"""Career evidence and privacy checks on guarded, synthetic _test records only."""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.api.schemas import JobIn
from app.core.config import settings
from app.core.security import utcnow
from app.db.models import (
    Job,
    JobSource,
    MatchResult,
)
from app.db.session import SessionLocal
from app.modules.career.analysis import role_matches
from app.modules.career.resources import learning_for
from app.services.jobs import store_job

P = "/api/v1"


def overview(client, **filters):
    response = client.post(P + "/career/overview", json=filters)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def career_jobs():
    with SessionLocal.begin() as db:
        source = JobSource(name="TEST ONLY Career source", source_type="manual")
        second = JobSource(name="TEST ONLY Second source", source_type="manual")
        db.add_all([source, second])
        db.flush()
        common = {
            "title": "TEST ONLY Data Analyst",
            "location": "Kochi",
            "published_at": datetime(2026, 9, 1, tzinfo=UTC),
        }
        a = store_job(
            db,
            JobIn(
                **common,
                employer="TEST ONLY A",
                description="Required skills\nPython and SQL\nPreferred skills\nDocker",
                source_id=source.id,
                external_id="a",
            ),
        )
        b = store_job(
            db,
            JobIn(
                **common,
                employer="TEST ONLY B",
                description="Required skills\nSQL\nPreferred skills\nAWS",
                source_id=source.id,
                external_id="b",
            ),
        )
        c = store_job(
            db,
            JobIn(
                **common,
                employer="TEST ONLY C",
                description="A role with no recognized technology requirements.",
                source_id=source.id,
                external_id="c",
            ),
        )
        duplicate = store_job(
            db,
            JobIn(
                **common,
                employer="TEST ONLY A",
                description=a.description,
                source_id=second.id,
                external_id="duplicate",
            ),
        )
        api = store_job(
            db,
            JobIn(
                title="TEST ONLY API Engineer",
                employer="TEST ONLY D",
                description="Required skills\nPython and FastAPI\nRequired qualifications\nBachelor degree or equivalent\nCertification required\n2 years experience\nPreferred skills\nDocker",
                source_id=source.id,
                external_id="d",
                location="Pune",
                published_at=datetime(2026, 10, 1, tzinfo=UTC),
            ),
        )
        return {
            "a": a.id,
            "b": b.id,
            "c": c.id,
            "api": api.id,
            "duplicate": duplicate.id,
            "source": source.id,
            "second": second.id,
        }


def skilled(candidate):
    candidate.post(P + "/profile/skills", json={"name": "Python"})
    candidate.post(
        P + "/profile/experience",
        json={
            "title": "Research Assistant",
            "employer": "PRIVATE EMPLOYER NOT FOR CAREER RESPONSE",
            "technologies": ["Python", "Git"],
            "responsibilities": "Built a Python demo",
        },
    )
    candidate.patch(P + "/profile", json={"summary": "Built a React prototype"})


def test_classification_no_resume_requirement_and_private_text(candidate, career_jobs):
    skilled(candidate)
    result = overview(candidate, target_role="Data analyst")
    skills = {s["key"]: s for s in result["candidate_skills"]}
    assert skills["python"]["status"] == "confirmed"
    assert skills["git"]["status"] == "resume_evidenced" and skills["git"]["used_for_role_overlap"]
    assert skills["react"]["status"] == "inferred"
    assert "PRIVATE EMPLOYER" not in str(result) and "Built a React prototype" not in str(result)
    assert all("text" not in source for s in skills.values() for source in s["sources"])


def test_denominators_required_preferred_duplicates_and_priority(candidate, career_jobs):
    skilled(candidate)
    result = overview(candidate, target_role="Data analyst")
    m = result["market"]
    assert m["relevant_listings"] == 3 and m["duplicate_records_excluded"] == 1
    assert m["listings_with_usable_requirements"] == 2
    stats = {s["key"]: s for s in result["skill_statistics"]}
    assert (
        stats["sql"]["count"] == 2
        and stats["sql"]["denominator"] == 3
        and stats["sql"]["percentage"] == 66.7
    )
    assert stats["sql"]["required_count"] == 2 and stats["sql"]["preferred_count"] == 0
    assert stats["docker"]["preferred_count"] == 1 and stats["docker"]["required_count"] == 0
    assert result["gaps"][0]["key"] == "sql"
    assert "python" not in [g["key"] for g in result["gaps"]]
    assert all(g["candidate_status"] == "not_evidenced" for g in result["gaps"])
    assert "not hiring probability" in result["gaps"][0]["priority_reason"]
    with SessionLocal() as db:
        for stat in stats.values():
            for req in stat["requirements"]:
                job = db.get(Job, req["job_id"])
                for ev in req["evidence"]:
                    assert getattr(job, ev["field"])[ev["start"] : ev["end"]] == ev["text"]


@pytest.mark.parametrize(
    ("kind", "expected"), [("required", {"python", "sql"}), ("preferred", {"docker", "aws"})]
)
def test_requirement_filter_does_not_change_denominator(candidate, career_jobs, kind, expected):
    result = overview(candidate, target_role="Data analyst", requirement_kind=kind)
    assert result["market"]["relevant_listings"] == 3
    assert {s["key"] for s in result["skill_statistics"]} == expected


def test_location_source_and_date_filters(candidate, career_jobs):
    skilled(candidate)
    result = overview(
        candidate,
        target_role="API Engineer",
        location="Pune",
        source_id=career_jobs["source"],
        published_after="2026-10-01T00:00:00Z",
        published_before="2026-10-02T00:00:00Z",
    )
    assert (
        result["market"]["relevant_listings"] == 1 and result["market"]["sources"][0]["count"] == 1
    )
    assert result["market"]["locations"] == [{"label": "Pune", "count": 1}]
    assert (
        overview(candidate, target_role="Data analyst", source_id=career_jobs["second"])["market"][
            "relevant_listings"
        ]
        == 1
    )
    assert (
        overview(candidate, published_after="2026-10-02T00:00:00Z")["market"]["relevant_listings"]
        == 0
    )


def test_unknown_publication_and_literal_location(candidate, career_jobs):
    with SessionLocal.begin() as db:
        db.get(Job, career_jobs["api"]).published_at = None
    assert (
        overview(candidate, target_role="API Engineer")["market"]["publication_range"][
            "unknown_count"
        ]
        == 1
    )
    assert (
        overview(candidate, target_role="API Engineer", published_after="2020-01-01T00:00:00Z")[
            "market"
        ]["relevant_listings"]
        == 0
    )
    assert overview(candidate, location="%%")["market"]["scoped_records"] == 0


def test_adjacent_roles_transition_and_extra_requirements(candidate, career_jobs):
    skilled(candidate)
    result = overview(candidate, target_role="Data analyst")
    role = next(r for r in result["roles"] if r["title"] == "TEST ONLY API Engineer")
    assert role["overlap"] == ["Python"] and "FastAPI" in role["missing_skills"]
    assert role["candidate_sources"][0]["status"] == "confirmed"
    assert {r["category"] for r in role["additional_requirements"]} == {
        "experience_requirements",
        "qualification_requirements",
        "unknown_constraints",
    }
    transition = next(t for t in result["transitions"] if t["destination_id"] == role["id"])
    assert (
        transition["origin"] == "Research Assistant"
        and transition["origin_kind"] == "recorded_experience"
    )
    assert transition["transferable_skills"] == ["Python"] and transition["origin_evidence"][0][
        "path"
    ].startswith("experience/")
    assert "inferred" in transition["evidence_strength"]
    assert all(r["representative_listings"] for r in result["roles"])


def test_selected_origin_from_collected_role_and_invalid_origin(candidate, career_jobs):
    skilled(candidate)
    result = overview(candidate, origin_role="TEST ONLY Data Analyst")
    assert result["transitions"] and all(
        t["origin_kind"] == "selected_exploration" for t in result["transitions"]
    )
    assert (
        candidate.post(
            P + "/career/overview", json={"origin_role": "Invented unobserved role"}
        ).status_code
        == 422
    )


def test_no_profile_no_data_and_no_skill_evidence(client, career_jobs):
    from tests.conftest import signup

    signup(client, profile=False)
    assert client.post(P + "/career/overview", json={}).status_code == 404
    client.post(P + "/profile", json={"name": "TEST ONLY Empty"})
    result = overview(client)
    assert (
        result["roles"] == []
        and result["gaps"] == []
        and result["learning"] == []
        and result["transitions"] == []
    )
    assert result["market"]["relevant_listings"] == 0 and result["skill_statistics"] == []
    result = overview(client, target_role="No observed role")
    assert result["market"]["relevant_listings"] == 0


def test_incomplete_empty_dataset(candidate):
    result = overview(candidate)
    assert result["candidate_skills"] == [] and result["market"]["stored_listing_records"] == 0
    assert result["gaps"] == [] and result["skill_statistics"] == []


def test_stale_closed_expired_integrated_jobs_excluded(candidate, career_jobs):
    skilled(candidate)
    now = utcnow()
    with SessionLocal.begin() as db:
        db.get(Job, career_jobs["a"]).status = "closed"
        db.get(Job, career_jobs["duplicate"]).status = "closed"
        db.get(Job, career_jobs["b"]).source_expires_at = now - timedelta(seconds=1)
        source = db.get(JobSource, career_jobs["source"])
        source.adapter_key = "himalayas"
        job = db.get(Job, career_jobs["api"])
        job.status = "active"
        job.last_verified_at = now - timedelta(days=2)
    result = overview(candidate, target_role="Data analyst")
    assert result["market"]["relevant_listings"] == 0
    assert result["market"]["excluded_unavailable"] == 5 and result["roles"] == []


def test_learning_verified_unverified_and_expired(candidate, career_jobs):
    skilled(candidate)
    result = overview(candidate, target_role="Data analyst")
    actions = {a["skill_key"]: a for a in result["learning"]}
    assert actions["sql"]["resources"][0]["verification_status"] == "verified"
    assert actions["sql"]["resources"][0]["url"].startswith("https://www.postgresql.org/")
    assert actions["sql"]["resources"][0]["verification_evidence"]
    assert actions["aws"]["resources"][0]["verification_status"] == "unverified_suggestion"
    assert actions["aws"]["resources"][0]["url"] is None
    expired = learning_for([next(g for g in result["gaps"] if g["key"] == "sql")], date(2027, 2, 1))
    assert expired[0]["resources"][0]["verification_status"] == "verification_stale"


def test_authorization_identity_rejection_and_other_candidate_isolation(
    candidate, other, career_jobs
):
    skilled(candidate)
    other.post(P + "/profile/skills", json={"name": "AWS"})
    mine = overview(candidate, target_role="Data analyst")
    theirs = overview(other, target_role="Data analyst")
    assert "aws" not in [g["key"] for g in theirs["gaps"]] and "aws" in [
        g["key"] for g in mine["gaps"]
    ]
    assert "python" not in [s["key"] for s in theirs["candidate_skills"]]
    assert (
        candidate.post(P + "/career/overview", json={"profile_id": str(uuid4())}).status_code == 422
    )
    candidate.post(P + "/auth/logout")
    assert candidate.post(P + "/career/overview", json={}).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"source_id": "bad"},
        {"source_id": str(uuid4())},
        {"requirement_kind": "mandatory-ish"},
        {"target_role": " "},
        {"published_after": "2026-10-28T00:00:00"},
        {"published_after": "2026-10-28T00:00:00Z", "published_before": "2026-10-01T00:00:00Z"},
        {"target_role": "x" * 151},
        {"candidate_id": str(uuid4())},
    ],
)
def test_invalid_inputs(candidate, body):
    response = candidate.post(P + "/career/overview", json=body)
    assert response.status_code in {404, 422}


def test_profile_job_preferences_change_recomputed_without_assessment_writes(
    candidate, career_jobs
):
    skilled(candidate)
    before = overview(candidate, target_role="Data analyst")
    candidate.post(P + "/profile/skills", json={"name": "SQL"})
    after = overview(candidate, target_role="Data analyst")
    assert before["input_fingerprint"] != after["input_fingerprint"] and "sql" not in [
        g["key"] for g in after["gaps"]
    ]
    candidate.patch(P + "/profile/preferences", json={"target_titles": ["API Engineer"]})
    assert overview(candidate)["market"]["target_roles"] == ["API Engineer"]
    with SessionLocal.begin() as db:
        db.get(Job, career_jobs["api"]).description = "Required skills\nPython and Kubernetes"
    changed = overview(candidate)
    assert "kubernetes" in [g["key"] for g in changed["gaps"]]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(MatchResult)) == 0


def test_unconfirmed_resume_status_no_fact_promotion_and_rejection(
    candidate, career_jobs, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "resume_storage_root", tmp_path / "resumes")
    from tests.test_resumes import processed

    _, run = processed(candidate)
    result = overview(candidate, target_role="Data analyst")
    assert result["roles"] == [] and candidate.get(P + "/profile").json()["skills"] == []
    assert all(
        s["status"] == "resume_evidenced" and s["used_for_role_overlap"] is False
        for s in result["candidate_skills"]
    )
    python = next(s for s in result["candidate_skills"] if s["key"] == "python")
    gap = next(g for g in result["gaps"] if g["key"] == "python")
    assert gap["action_kind"] == "review_existing_evidence"
    assert all("excerpt" not in str(s) for s in result["candidate_skills"])
    candidate.post(
        f"{P}/extractions/{run['id']}/review",
        json={
            "expected_revision": run["revision"],
            "items": [{"id": python["sources"][0]["proposal_id"], "decision": "rejected"}],
        },
    )
    updated = overview(candidate, target_role="Data analyst")
    assert "python" not in [s["key"] for s in updated["candidate_skills"]]


def test_bounded_partial_population_is_explicit(candidate, career_jobs, monkeypatch):
    from app.modules.career import service

    monkeypatch.setattr(service, "MAX_LISTINGS", 2)
    result = overview(candidate, target_role="Data analyst")
    assert (
        result["market"]["population_truncated"] is True
        and result["market"]["analyzed_records"] == 2
    )
    assert any("Partial population" in n for n in result["market"]["limitations"])
    assert all(
        s["denominator"] == result["market"]["relevant_listings"]
        for s in result["skill_statistics"]
    )


@pytest.mark.parametrize(
    ("title", "target", "match"),
    [
        ("Senior Software Developer", "Software engineer", True),
        ("Java engineer", "JavaScript engineer", False),
        ("Data analyst", "Data analyst", True),
        ("Product designer", "Data analyst", False),
    ],
)
def test_existing_role_aliases_without_title_only_fit(title, target, match):
    assert role_matches(title, target) == match


def test_confirmed_resume_provenance_and_deleted_document_retention(
    candidate, career_jobs, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "resume_storage_root", tmp_path / "private")
    from tests.test_resumes import confirm, confirmation, decide, processed

    resume, run = processed(candidate)
    item = next(
        p
        for p in run["proposals"]
        if p["category"] == "skill" and p["original_value"]["canonical"] == "python"
    )
    run = decide(candidate, run, [{"id": item["id"], "decision": "accepted"}])
    assert confirm(candidate, run, confirmation(candidate, run, [item["id"]])).status_code == 200
    result = overview(candidate, target_role="Data analyst")
    skill = next(s for s in result["candidate_skills"] if s["key"] == "python")
    assert skill["status"] == "confirmed" and any(
        s["kind"] == "confirmed_resume_record" for s in skill["sources"]
    )
    assert candidate.delete(f"{P}/resumes/{resume['id']}").status_code == 200
    retained = next(s for s in overview(candidate)["candidate_skills"] if s["key"] == "python")
    assert retained["status"] == "confirmed" and all(
        s["kind"] == "profile_record" for s in retained["sources"]
    )


@pytest.mark.parametrize(
    ("title", "target"),
    [
        ("JavaScript engineer", "Java engineer"),
        ("C++ engineer", "Java engineer"),
        ("Medical Analyst", "Financial Analyst"),
    ],
)
def test_role_filters_keep_distinct_technology_and_domain_words(title, target):
    assert role_matches(title, target) is False


def test_alias_equivalence_and_incidental_mentions_in_career_counts(candidate):
    with SessionLocal.begin() as db:
        store_job(
            db,
            JobIn(
                title="TEST ONLY Analyst",
                employer="TEST ONLY",
                description="Required skills\nPostgres and PostgreSQL and JavaScript; Java is not required",
            ),
        )
    candidate.post(P + "/profile/skills", json={"name": "Postgres"})
    result = overview(candidate, target_role="Analyst")
    stats = {s["key"]: s for s in result["skill_statistics"]}
    assert set(stats) == {"postgresql", "javascript"}
    assert (
        stats["postgresql"]["count"] == 1 and stats["postgresql"]["candidate_status"] == "confirmed"
    )
    assert "postgresql" not in [g["key"] for g in result["gaps"]]


def test_career_database_errors_are_redacted_and_recoverable(candidate, monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app.modules.career import service

    def fail(*args, **kwargs):
        raise OperationalError("PRIVATE SQL AND PATH", {}, Exception("PRIVATE RESUME CONTENT"))

    monkeypatch.setattr(service, "retrieve", fail)
    response = candidate.post(P + "/career/overview", json={})
    assert response.status_code == 503
    assert "PRIVATE" not in response.text and "Database temporarily unavailable" in response.text


def test_concurrent_ingestion_uses_one_snapshot_and_next_request_sees_update(
    candidate, monkeypatch
):
    from app.modules.career import service

    original = service.retrieve
    inserted = False

    def concurrent_insert(db, filters, now):
        nonlocal inserted
        assert db.connection().get_isolation_level() == "REPEATABLE READ"
        if not inserted:
            with SessionLocal.begin() as writer:
                store_job(
                    writer,
                    JobIn(
                        title="TEST ONLY Analyst",
                        employer="TEST ONLY",
                        description="Required skills\nPython",
                    ),
                )
            inserted = True
        return original(db, filters, now)

    monkeypatch.setattr(service, "retrieve", concurrent_insert)
    first = overview(candidate, target_role="Analyst")
    assert first["market"]["stored_listing_records"] == first["market"]["relevant_listings"] == 0
    second = overview(candidate, target_role="Analyst")
    assert second["market"]["stored_listing_records"] == second["market"]["relevant_listings"] == 1
    assert second["skill_statistics"][0]["denominator"] == 1


def test_ingestion_commit_between_population_count_and_evidence_query(
    candidate, career_jobs, monkeypatch
):
    from sqlalchemy import event

    from app.modules.career import service

    original = service.retrieve
    committed = False
    skilled(candidate)

    def retrieve_with_interleaved_commit(db, filters, now):
        connection = db.connection()
        assert connection.get_isolation_level() == "REPEATABLE READ"

        def after_count(conn, cursor, statement, parameters, context, executemany):
            nonlocal committed
            if committed or not " ".join(statement.lower().split()).startswith("select count(*)"):
                return
            committed = True
            # This is a separate committed PostgreSQL transaction while the
            # dashboard transaction remains open between count and row reads.
            with SessionLocal.begin() as writer:
                writer.get(Job, career_jobs["a"]).description = "Required skills\nKubernetes"
                writer.get(Job, career_jobs["b"]).status = "closed"
                store_job(
                    writer,
                    JobIn(
                        title="TEST ONLY Data Analyst",
                        employer="TEST ONLY New",
                        description="Required skills\nDocker",
                        location="Kochi",
                    ),
                )

        event.listen(connection, "after_cursor_execute", after_count)
        try:
            return original(db, filters, now)
        finally:
            event.remove(connection, "after_cursor_execute", after_count)

    monkeypatch.setattr(service, "retrieve", retrieve_with_interleaved_commit)
    first = overview(candidate, target_role="Data analyst")
    assert committed
    assert first["market"]["stored_listing_records"] == 5
    assert first["market"]["relevant_listings"] == 3
    first_stats = {s["key"]: s for s in first["skill_statistics"]}
    assert first_stats["sql"]["count"] == 2
    assert "kubernetes" not in first_stats
    assert all(s["denominator"] == 3 for s in first_stats.values())

    second = overview(candidate, target_role="Data analyst")
    assert second["market"]["stored_listing_records"] == 6
    assert second["market"]["relevant_listings"] == 4
    second_stats = {s["key"]: s for s in second["skill_statistics"]}
    assert second_stats["sql"]["count"] == 1 and second_stats["kubernetes"]["count"] == 1
    assert all(s["denominator"] == 4 for s in second_stats.values())


def test_career_transaction_cleanup_rollback_and_pool_isolation_reset(candidate, monkeypatch):
    from sqlalchemy import text

    from app.db.session import engine
    from app.modules.career import service

    sessions = []
    original = service.retrieve

    def successful_read(db, filters, now):
        sessions.append(db)
        assert db.connection().get_isolation_level() == "REPEATABLE READ"
        return original(db, filters, now)

    monkeypatch.setattr(service, "retrieve", successful_read)
    overview(candidate)
    assert not sessions[-1].in_transaction()
    assert engine.pool.checkedout() == 0

    def actual_database_failure(db, filters, now):
        sessions.append(db)
        db.execute(text("SELECT 1/0"))

    monkeypatch.setattr(service, "retrieve", actual_database_failure)
    response = candidate.post(P + "/career/overview", json={})
    assert response.status_code == 503
    assert not sessions[-1].in_transaction()
    assert engine.pool.checkedout() == 0
    with SessionLocal() as ordinary:
        assert ordinary.connection().get_isolation_level() == "READ COMMITTED"
        assert (
            ordinary.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND state='idle in transaction'"
                )
            )
            == 0
        )

    monkeypatch.setattr(service, "retrieve", original)
    assert overview(candidate)["market"]["stored_listing_records"] == 0
    assert candidate.get(P + "/profile").status_code == 200
    assert engine.pool.checkedout() == 0
