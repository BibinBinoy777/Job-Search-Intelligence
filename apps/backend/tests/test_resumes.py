"""Synthetic documents and candidates are restricted to the guarded _test database."""

import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.db.models import (
    Resume,
    ResumeConfirmation,
    ResumeExtraction,
    ResumeProposal,
    ResumeVersion,
)
from app.db.session import SessionLocal
from app.modules.resumes import extraction, review, service
from app.modules.resumes.qualification_extraction import extract
from app.modules.resumes.storage import PrivateStorage
from app.modules.resumes.validation import MIMES, ResumeError
from tests.resume_fixtures import docx, pdf

P = "/api/v1"


@pytest.fixture(autouse=True)
def private_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "resume_storage_root", tmp_path / "private")


def upload(client, content=None, kind="pdf", resume_id=None, filename=None, mime=None):
    return client.post(
        P + "/resumes" + (f"/{resume_id}/versions" if resume_id else ""),
        content=pdf() if content is None else content,
        headers={
            "Content-Type": mime or MIMES[kind],
            "X-Resume-Filename": filename or f"TEST-ONLY.{kind}",
        },
    )


def processed(client, content=None, kind="pdf"):
    response = upload(client, content, kind)
    assert response.status_code == 201, response.text
    resume = response.json()
    response = client.post(
        f"{P}/resumes/{resume['id']}/process", json={"version_id": resume["versions"][0]["id"]}
    )
    assert response.status_code == 200, response.text
    return resume, response.json()


def decide(client, run, items):
    response = client.post(
        f"{P}/extractions/{run['id']}/review",
        json={"expected_revision": run["revision"], "items": items},
    )
    assert response.status_code == 200, response.text
    return response.json()


def confirmation(client, run, ids, **extra):
    preview = client.get(f"{P}/extractions/{run['id']}/preview").json()
    return {
        "request_key": str(uuid4()),
        "expected_revision": preview["revision"],
        "expected_profile_fingerprint": preview["profile_fingerprint"],
        "item_ids": ids,
        **extra,
    }


def confirm(client, run, body):
    return client.post(f"{P}/extractions/{run['id']}/confirm", json=body)


@pytest.mark.parametrize("kind", ["pdf", "docx"])
def test_real_parser_version_evidence_and_no_automatic_profile_change(candidate, kind):
    before = candidate.get(P + "/profile").json()
    resume, run = processed(candidate, pdf(pages=2) if kind == "pdf" else docx(), kind)
    assert run["status"] == "review_required", run
    assert {p["category"] for p in run["proposals"]} == {
        "skill",
        "experience",
        "education",
        "certification",
        "project",
        "language",
        "summary",
    }
    assert run["quality"]["ocr_performed"] is False
    assert run["quality"]["pages"] == (2 if kind == "pdf" else None)
    with SessionLocal() as db:
        stored = db.get(ResumeExtraction, run["id"])
        for proposal in run["proposals"]:
            ev = proposal["evidence"]
            segment = next(s for s in stored.segments if s["id"] == ev["segment_id"])
            assert segment["text"][ev["start"] : ev["end"]] == ev["excerpt"]
            assert ev["version_id"] == resume["versions"][0]["id"] == run["version_id"]
        if kind == "docx":
            assert any("English" in s["text"] and "table" in s["part"] for s in stored.segments)
        else:
            assert [s["page"] for s in stored.segments] == [1, 2]
    assert candidate.get(P + "/profile").json() == before
    again = candidate.post(
        f"{P}/resumes/{resume['id']}/process", json={"version_id": run["version_id"]}
    ).json()
    for field in ["started_at", "finished_at"]:
        assert datetime.fromisoformat(again.pop(field)) == datetime.fromisoformat(run.pop(field))
    assert again == run
    assert "storage_ref" not in str(resume) and str(settings.resume_storage_root) not in str(resume)
    assert resume["versions"][0]["scan_status"] == "not_configured"


@pytest.mark.parametrize(
    ("filename", "mime", "content", "status"),
    [
        ("resume.exe", "application/pdf", b"%PDF-1.4", 422),
        ("resume.pdf", "text/plain", b"%PDF-1.4", 422),
        ("resume.pdf", "application/pdf", b"not a PDF", 422),
        ("resume.docx", MIMES["docx"], b"not a ZIP", 422),
        ("resume.pdf", "application/pdf", b"%PDF-broken", 422),
        ("../resume.pdf", "application/pdf", b"%PDF-", 422),
        ("C:resume.pdf", "application/pdf", b"%PDF-", 422),
        ("resume.pdf", "application/pdf", b"", 413),
    ],
)
def test_bad_uploads_write_nothing(candidate, filename, mime, content, status):
    response = upload(candidate, content, filename=filename, mime=mime)
    assert response.status_code == status, response.text
    assert candidate.get(P + "/resumes").json() == []
    assert list(settings.resume_storage_root.rglob("*.blob")) == []
    assert (
        "Traceback" not in response.text and str(settings.resume_storage_root) not in response.text
    )


def test_password_macro_archive_and_oversize_rejected(candidate, monkeypatch):
    assert upload(candidate, pdf(password="secret")).status_code == 422
    for extra in [
        {"word/vbaProject.bin": b"code"},
        {"../evil.xml": b"x"},
        {"word/huge.xml": b"x" * 100000},
    ]:
        assert upload(candidate, docx(extra=extra), "docx").status_code == 422
    monkeypatch.setattr(settings, "resume_max_bytes", 1024)
    assert upload(candidate, b"%PDF-" + b"x" * 2048).status_code == 413
    # A streamed request is bounded even without relying on Content-Length.
    assert (
        candidate.post(
            P + "/resumes",
            content=iter([b"%PDF-", b"x" * 2048]),
            headers={"Content-Type": MIMES["pdf"], "X-Resume-Filename": "r.pdf"},
        ).status_code
        == 413
    )
    assert list(settings.resume_storage_root.rglob("*.blob")) == []


@pytest.mark.parametrize(
    ("content", "kind", "code"),
    [
        (pdf(lines=[]), "pdf", "empty_text"),
        (docx(lines=[]), "docx", "empty_text"),
        (pdf(image=True), "pdf", "ocr_required"),
    ],
)
def test_no_usable_text_honest_failure(candidate, content, kind, code):
    _, run = processed(candidate, content, kind)
    assert run["status"] == "failed" and run["error_code"] == code
    assert run["proposals"] == []
    assert candidate.get(P + "/profile").json()["skills"] == []


def test_parser_bounds_timeout_and_safe_retry(candidate, monkeypatch):
    resume = upload(candidate).json()
    original = service.parse_document

    def timeout(*args, **kwargs):
        raise ResumeError("parser_timeout")

    monkeypatch.setattr(service, "parse_document", timeout)
    run = candidate.post(
        f"{P}/resumes/{resume['id']}/process", json={"version_id": resume["versions"][0]["id"]}
    ).json()
    assert run["error_code"] == "parser_timeout"
    monkeypatch.setattr(service, "parse_document", original)
    retried = candidate.post(
        f"{P}/resumes/{resume['id']}/process", json={"version_id": run["version_id"]}
    ).json()
    assert (
        retried["id"] == run["id"]
        and retried["attempts"] == 2
        and retried["status"] == "review_required"
    )
    monkeypatch.setattr(settings, "resume_max_text_chars", 10)
    with pytest.raises(ResumeError) as error:
        extraction.parse_document(pdf(), "pdf")
    assert error.value.code == "document_limit"


def test_subprocess_exceptions_and_gate_release(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("private", 1)

    monkeypatch.setattr(extraction.subprocess, "run", timeout)
    for _ in range(3):
        with pytest.raises(ResumeError) as error:
            extraction.parse_document(b"private", "pdf")
        assert error.value.code == "parser_timeout"


def test_versions_same_checksum_keep_distinct_files_and_quota(candidate, monkeypatch):
    content = pdf()
    first = upload(candidate, content).json()
    second = upload(candidate, content, resume_id=first["id"]).json()
    assert second["version_count"] == 2
    assert len({v["id"] for v in second["versions"]}) == 2
    assert len({v["checksum"] for v in second["versions"]}) == 1
    assert len(list(settings.resume_storage_root.rglob("*.blob"))) == 2
    for version in second["versions"]:
        response = candidate.get(f"{P}/resumes/{first['id']}/versions/{version['id']}/download")
        assert (
            response.content == content and "attachment" in response.headers["content-disposition"]
        )
    monkeypatch.setattr(settings, "resume_quota_bytes", len(content) * 2)
    assert upload(candidate, content, resume_id=first["id"]).status_code == 409


def test_all_cross_candidate_endpoints_and_invalid_ids(candidate, other):
    resume, run = processed(candidate)
    r, v, e = resume["id"], run["version_id"], run["id"]
    operations = [
        ("GET", f"/resumes/{r}", None),
        ("GET", f"/resumes/{r}/versions/{v}/download", None),
        ("GET", f"/resumes/{r}/extractions", None),
        ("GET", f"/extractions/{e}", None),
        ("GET", f"/extractions/{e}/preview", None),
        ("POST", f"/resumes/{r}/process", {"version_id": v}),
        (
            "POST",
            f"/extractions/{e}/review",
            {
                "expected_revision": run["revision"],
                "items": [{"id": run["proposals"][0]["id"], "decision": "accepted"}],
            },
        ),
        (
            "POST",
            f"/extractions/{e}/confirm",
            confirmation(candidate, run, [run["proposals"][0]["id"]]),
        ),
        ("DELETE", f"/resumes/{r}", None),
    ]
    for method, path, body in operations:
        response = (
            other.request(method, P + path, json=body) if body else other.request(method, P + path)
        )
        assert response.status_code == 404, (path, response.text)
    assert upload(other, resume_id=r).status_code == 404
    assert candidate.get(P + "/resumes/not-a-uuid").status_code == 422
    assert candidate.get(f"{P}/resumes/{r}").status_code == 200


def test_review_edit_reject_pending_explicit_confirm_and_retry(candidate):
    _, run = processed(candidate)
    skills = [p for p in run["proposals"] if p["category"] == "skill"]
    a, b, c = skills[:3]
    run = decide(
        candidate,
        run,
        [
            {"id": a["id"], "decision": "edited_accepted", "value": {"name": "TypeScript"}},
            {"id": b["id"], "decision": "rejected"},
            {"id": c["id"], "decision": "pending"},
        ],
    )
    assert candidate.get(P + "/profile").json()["skills"] == []
    assert confirm(candidate, run, confirmation(candidate, run, [c["id"]])).status_code == 409
    body = confirmation(candidate, run, [a["id"]])
    response = confirm(candidate, run, body)
    assert response.status_code == 200, response.text
    assert response.json()["matching_requires_refresh"] is True
    assert [s["name"] for s in candidate.get(P + "/profile").json()["skills"]] == ["TypeScript"]
    assert confirm(candidate, run, body).json() == response.json()  # lost-response retry
    body["item_ids"] = [b["id"]]
    assert confirm(candidate, run, body).status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ResumeConfirmation)) == 1
        assert db.get(ResumeProposal, b["id"]).applied_at is None
        assert db.get(ResumeProposal, c["id"]).applied_at is None


def test_duplicate_aliases_and_concurrent_profile_revision(candidate):
    candidate.post(P + "/profile/skills", json={"name": "Postgres"})
    _, run = processed(candidate)
    p = next(
        p
        for p in run["proposals"]
        if p["category"] == "skill" and p["original_value"]["canonical"] == "postgresql"
    )
    run = decide(candidate, run, [{"id": p["id"], "decision": "accepted"}])
    body = confirmation(candidate, run, [p["id"]])
    candidate.patch(P + "/profile", json={"headline": "Concurrent manual edit"})
    assert confirm(candidate, run, body).status_code == 409
    body = confirmation(candidate, run, [p["id"]])
    result = confirm(candidate, run, body).json()
    assert (
        result["changes"][0]["action"] == "duplicate"
        and result["matching_requires_refresh"] is False
    )
    assert len(candidate.get(P + "/profile").json()["skills"]) == 1
    # A review edit also invalidates an old preview.
    q = next(p for p in run["proposals"] if p["category"] == "education")
    stale = confirmation(candidate, run, [q["id"]])
    latest = candidate.get(f"{P}/extractions/{run['id']}").json()
    decide(candidate, latest, [{"id": q["id"], "decision": "accepted"}])
    assert confirm(candidate, run, stale).status_code == 409


def test_conflicts_preserve_existing_and_need_explicit_resolution(candidate):
    candidate.patch(P + "/profile", json={"summary": "Existing manual summary"})
    candidate.post(
        P + "/profile/experience",
        json={
            "title": "Software Engineer",
            "employer": "TEST ONLY Labs",
            "responsibilities": "Manual history",
        },
    )
    _, run = processed(candidate)
    selected = [p for p in run["proposals"] if p["category"] in {"summary", "experience"}]
    run = decide(candidate, run, [{"id": p["id"], "decision": "accepted"} for p in selected])
    ids = [p["id"] for p in selected]
    assert confirm(candidate, run, confirmation(candidate, run, ids)).status_code == 409
    body = confirmation(
        candidate,
        run,
        ids,
        resolutions={
            p["id"]: "skip" if p["category"] == "summary" else "add_separate" for p in selected
        },
    )
    assert confirm(candidate, run, body).status_code == 200
    profile = candidate.get(P + "/profile").json()
    assert profile["summary"] == "Existing manual summary" and len(profile["experience"]) == 2
    assert any(p["responsibilities"] == "Manual history" for p in profile["experience"])


def test_multi_update_database_failure_rolls_back_every_marker(candidate, monkeypatch):
    _, run = processed(candidate)
    items = [p for p in run["proposals"] if p["category"] == "skill"][:2]
    run = decide(candidate, run, [{"id": p["id"], "decision": "accepted"} for p in items])
    body = confirmation(candidate, run, [p["id"] for p in items])
    original = review.candidates.add_skill
    calls = 0

    def failing(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OperationalError("hidden path", {}, Exception("private document"))
        return original(*args, **kwargs)

    monkeypatch.setattr(review.candidates, "add_skill", failing)
    response = confirm(candidate, run, body)
    assert response.status_code == 503 and "private document" not in response.text
    assert candidate.get(P + "/profile").json()["skills"] == []
    latest = candidate.get(f"{P}/extractions/{run['id']}").json()
    assert latest["revision"] == run["revision"] and all(
        p["applied_at"] is None for p in latest["proposals"]
    )
    monkeypatch.setattr(review.candidates, "add_skill", original)
    assert confirm(candidate, run, body).status_code == 200


def test_concurrent_confirm_serializes_and_replays(candidate):
    _, run = processed(candidate)
    p = next(p for p in run["proposals"] if p["category"] == "skill")
    run = decide(candidate, run, [{"id": p["id"], "decision": "accepted"}])
    body = confirmation(candidate, run, [p["id"]])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: confirm(candidate, run, body), range(2)))
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].json() == results[1].json()
    assert len(candidate.get(P + "/profile").json()["skills"]) == 1


def test_delete_pending_retry_cascades_but_preserves_profile(candidate, monkeypatch):
    resume, run = processed(candidate)
    p = next(p for p in run["proposals"] if p["category"] == "skill")
    run = decide(candidate, run, [{"id": p["id"], "decision": "accepted"}])
    assert confirm(candidate, run, confirmation(candidate, run, [p["id"]])).status_code == 200
    original = PrivateStorage.delete

    def fail(*args):
        raise PermissionError("private path")

    monkeypatch.setattr(PrivateStorage, "delete", fail)
    response = candidate.delete(f"{P}/resumes/{resume['id']}")
    assert response.status_code == 202 and response.json()["status"] == "deletion_pending"
    assert candidate.get(f"{P}/extractions/{run['id']}").status_code == 404
    assert (
        candidate.post(
            f"{P}/resumes/{resume['id']}/process", json={"version_id": run["version_id"]}
        ).status_code
        == 409
    )
    monkeypatch.setattr(PrivateStorage, "delete", original)
    assert candidate.delete(f"{P}/resumes/{resume['id']}").json()["status"] == "deleted"
    assert list(settings.resume_storage_root.rglob("*.blob")) == []
    with SessionLocal() as db:
        for model in [Resume, ResumeVersion, ResumeExtraction, ResumeProposal, ResumeConfirmation]:
            assert db.scalar(select(func.count()).select_from(model)) == 0
    assert len(candidate.get(P + "/profile").json()["skills"]) == 1


def test_final_delete_commit_failure_tombstone_recoverable(candidate, monkeypatch):
    resume, _ = processed(candidate)
    original = SessionLocal.class_.commit
    calls = 0

    def fail_second(session):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OperationalError("hidden", {}, Exception("failed"))
        return original(session)

    monkeypatch.setattr(SessionLocal.class_, "commit", fail_second)
    assert candidate.delete(f"{P}/resumes/{resume['id']}").status_code == 503
    monkeypatch.setattr(SessionLocal.class_, "commit", original)
    assert candidate.get(f"{P}/resumes/{resume['id']}").json()["status"] == "deletion_pending"
    assert list(settings.resume_storage_root.rglob("*.blob")) == []
    assert candidate.delete(f"{P}/resumes/{resume['id']}").json()["status"] == "deleted"


def test_upload_commit_failure_cleans_private_bytes(candidate, monkeypatch):
    def fail(*args):
        raise OperationalError("hidden", {}, Exception("failed"))

    monkeypatch.setattr(SessionLocal.class_, "commit", fail)
    assert upload(candidate).status_code == 503
    assert list(settings.resume_storage_root.rglob("*.blob")) == []
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Resume)) == 0


def test_matching_invalidated_only_for_confirmed_owner(candidate, other, seeded_jobs):
    candidate.post(P + "/profile/skills", json={"name": "Java"})
    other.post(P + "/profile/skills", json={"name": "Java"})
    for client in [candidate, other]:
        assert client.post(P + "/matches/refresh", json={}).status_code == 200
    before = other.get(P + "/matching/status").json()
    _, run = processed(candidate)
    unchanged = candidate.get(P + "/matching/status").json()
    assert unchanged["stale_results"] == 0
    p = next(
        p
        for p in run["proposals"]
        if p["category"] == "skill" and p["original_value"]["canonical"] == "python"
    )
    run = decide(candidate, run, [{"id": p["id"], "decision": "accepted"}])
    assert candidate.get(P + "/matching/status").json()["stale_results"] == 0
    assert (
        confirm(candidate, run, confirmation(candidate, run, [p["id"]])).json()[
            "matching_requires_refresh"
        ]
        is True
    )
    assert candidate.get(P + "/matching/status").json()["stale_results"] == 2
    assert other.get(P + "/matching/status").json() == before


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Degree | School | 2020 - 2024", "unknown"),
        ("Degree | School | 2020 - 2024 | not completed", "unknown"),
        ("Degree | School | expected 2027", "in_progress"),
        ("Degree | School | Graduated", "completed"),
    ],
)
def test_ambiguous_education_dates_and_negation(line, expected):
    result = extract([{"id": 0, "text": "Education\n" + line, "page": 1, "part": "page"}])
    assert result[0]["original_value"]["completion_status"] == expected
    assert result[0]["original_value"]["start_date"] is None


def test_incidental_and_negated_skill_mentions_do_not_become_qualifications():
    result = extract(
        [
            {
                "id": 0,
                "text": "Contact Python Club\nEducation\nPython | University\nSkills\nI do not know Java. Python and Postgres\nExperience\nEngineer at Labs | 2020 - Present",
                "page": 1,
                "part": "page",
            }
        ]
    )
    skills = [p["original_value"]["canonical"] for p in result if p["category"] == "skill"]
    assert set(skills) == {"python", "postgresql"}
    experience = next(p["original_value"] for p in result if p["category"] == "experience")
    assert (
        experience["start_date"] is None
        and experience["is_current"] is True
        and experience["end_date"] is None
    )


def test_storage_rejects_public_root_and_path_traversal(monkeypatch):
    storage = PrivateStorage()
    for ref in ["../../a", "/tmp/a", str(uuid4()) + "/../x.blob"]:
        with pytest.raises(ValueError):
            storage.path(ref)
    from pathlib import Path

    monkeypatch.setattr(
        settings, "resume_storage_root", Path(__file__).resolve().parents[2] / "frontend" / "public"
    )
    with pytest.raises(ValueError):
        PrivateStorage()


@pytest.mark.parametrize(
    "category",
    ["skill", "experience", "education", "summary", "certification", "project", "language"],
)
def test_each_supported_category_confirmed_as_reviewed_matching_input(candidate, category):
    _, run = processed(candidate)
    proposal = next(p for p in run["proposals"] if p["category"] == category)
    run = decide(candidate, run, [{"id": proposal["id"], "decision": "accepted"}])
    response = confirm(candidate, run, confirmation(candidate, run, [proposal["id"]]))
    assert response.status_code == 200, response.text
    assert response.json()["matching_requires_refresh"] is True
    profile = candidate.get(P + "/profile").json()
    if category == "education":
        assert profile["education"][0]["completion_status"] == "in_progress"
        assert profile["education"][0]["start_date"] is None
    elif category == "experience":
        assert profile["experience"][0]["is_current"] is True
        assert profile["experience"][0]["end_date"] is None
        assert profile["experience"][0]["achievements"] is None
    elif category == "certification":
        assert profile["certifications"][0].endswith("validity not verified")
    latest = candidate.get(f"{P}/extractions/{run['id']}").json()
    repeated = confirm(candidate, latest, confirmation(candidate, latest, [proposal["id"]]))
    assert (
        repeated.status_code == 200 and repeated.json()["changes"][0]["action"] == "already_applied"
    )
    assert candidate.get(P + "/profile").json() == profile


def test_unauthenticated_and_invalid_request_bodies(client, candidate):
    # Explicitly drop this client's authenticated session for the anonymous check.
    candidate.post(P + "/auth/logout")
    assert client.get(P + "/resumes").status_code == 401
    assert upload(client).status_code == 401


@pytest.mark.parametrize(
    "extra",
    [
        {
            "word/_rels/document.xml.rels": '<Relationships><Relationship TargetMode="External" Type="external/template" Target="https://example.invalid/private"/></Relationships>'
        },
        {
            "word/header1.xml": '<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///private">]><x>&secret;</x>'
        },
    ],
)
def test_external_relationships_and_entities_rejected(candidate, extra):
    response = upload(candidate, docx(extra=extra), "docx")
    assert response.status_code == 422
    assert "file:///" not in response.text and "example.invalid" not in response.text


def test_limits_pages_sections_and_invalid_docx_xml(candidate, monkeypatch):
    monkeypatch.setattr(settings, "resume_max_pages", 1)
    assert upload(candidate, pdf(pages=2)).status_code == 422
    monkeypatch.setattr(settings, "resume_max_sections", 1)
    _, run = processed(candidate, docx(), "docx")
    assert run["error_code"] == "document_limit"
    assert upload(candidate, b"PK\x03\x04broken", "docx").status_code == 422
