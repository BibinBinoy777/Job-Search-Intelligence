import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.db.models import Job, JobRequirementAnalysis, MatchingRefresh, MatchResult
from app.db.session import SessionLocal
from app.main import app
from app.modules.matching.candidate import analyze_candidate
from app.modules.matching.config import CONFIG, RankingConfig
from app.modules.matching.engine import evaluate
from app.modules.matching.evaluation import job_input, metrics, run_evaluation
from app.modules.matching.features import merged_years
from app.modules.matching.requirements import analyze_requirements
from app.modules.matching.skills import normalize_skill

P = "/api/v1"
DATA = Path(__file__).resolve().parents[3] / "data/evaluation/matching-rubric-v1.json"


@pytest.fixture
def builder():
    return copy.deepcopy(json.loads(DATA.read_text())["candidates"]["builder"])


def outcome(candidate, **job):
    now = datetime(2026, 10, 27, tzinfo=UTC)
    j = job_input(
        {
            "title": "Software engineer",
            "description": "Required skills\nPython and Postgres.",
            **job,
        },
        now,
    )
    return evaluate(candidate, j, analyze_requirements(j), now)


@pytest.mark.parametrize(
    ("alias", "key"),
    [
        ("JS", "javascript"),
        ("Postgres", "postgresql"),
        ("ML", "machine_learning"),
        ("NLP", "natural_language_processing"),
        ("Java", "java"),
        ("C++", "cpp"),
        ("C#", "csharp"),
        ("Go", "golang"),
    ],
)
def test_aliases_are_precise(alias, key):
    assert normalize_skill(alias) == key
    assert normalize_skill("Java") != normalize_skill("JavaScript")


def test_explicit_and_derived_evidence_negation_and_alias_dedup(builder):
    builder["summary"] = "I do not know Java. Built a PyTorch prototype."
    evidence = analyze_candidate(builder)
    assert evidence["skills"]["python"][0]["kind"] == "explicit"
    assert evidence["skills"]["pytorch"][0]["kind"] == "derived"
    assert "java" not in evidence["skills"]
    result = outcome(builder, description="Required skills\nPostgreSQL and Postgres and Python.")
    assert len(result["skills"]["required"]) == 2
    assert result["features"]["required_skills"]["value"] == 1


def test_requirements_required_preferred_incidental_exact_spans():
    job = {
        "title": "Engineer",
        "description": "About us\nOur website uses Java.\nRequirements\nPython is required; AWS is preferred.\nNice to have\nPostgres.\nBenefits\nLearn React in our club.",
        "skills": [],
    }
    result = analyze_requirements(job)
    assert [s["key"] for s in result["required_skills"]] == ["python"]
    assert {s["key"] for s in result["preferred_skills"]} == {"aws", "postgresql"}
    assert {s["key"] for s in result["incidental_skills"]} == {"java", "react"}
    for item in (
        result["required_skills"] + result["preferred_skills"] + result["incidental_skills"]
    ):
        for ev in item["evidence"]:
            assert job[ev["field"]][ev["start"] : ev["end"]] == ev["text"]


def test_structured_requirements_and_experience_are_authoritative(builder):
    result = outcome(
        builder,
        description="Our company likes Java.",
        skills=[{"name": "Python", "kind": "required"}, {"name": "Postgres", "kind": "preferred"}],
        experience_min=4,
    )
    assert result["features"]["experience"]["value"] < 1
    assert result["features"]["experience"]["details"]["required_minimum"] == 4
    assert result["skills"]["required"][0]["job_evidence"][0]["origin"] == "structured"


@pytest.mark.parametrize(
    "description", ["Must not use Python.", "Python is not required.", "Must know Python or Java."]
)
def test_negated_and_alternative_skills_not_invented_as_mandatory(description):
    assert analyze_requirements({"description": description})["required_skills"] == []


def test_unknown_does_not_mean_deficiency_or_zero(builder):
    result = outcome(builder, description="Must know Kubernetes.")
    item = result["skills"]["required"][0]
    assert item["state"] == "not_evidenced" and not item["candidate_evidence"]
    assert result["eligibility"]["status"] == "unknown"
    assert not result["eligibility"]["excluded"]
    assert "does not prove" in result["concerns"][0]["text"]
    result = outcome(builder, description="Build useful systems.")
    assert result["features"]["required_skills"]["value"] is None


def test_incomplete_profile_preferences_only_and_resume_independence(builder):
    empty = {
        "preferences": {"target_titles": ["Software engineer"], "work_arrangements": ["remote"]}
    }
    assert outcome(empty)["score"] is None
    first = outcome(builder)
    builder["resume_uploaded"] = False
    assert outcome(builder)["score"] == first["score"]


def test_country_preferences_are_not_residence_and_protected_traits_unused(builder):
    builder["preferences"].pop("current_country")
    builder["preferences"]["locations"] = ["United States"]
    result = outcome(builder, location_restrictions=["United States"])
    assert result["eligibility"]["status"] != "confirmed_mismatch"
    builder["preferences"]["current_country"] = "India"
    result = outcome(builder, location_restrictions=["United States"])
    assert result["eligibility"]["status"] == "confirmed_mismatch"
    before = outcome(builder)["score"]
    builder.update(
        {
            "name": "Different name",
            "gender": "different",
            "age": 90,
            "religion": "different",
            "disability": "different",
        }
    )
    builder["headline"] = "Young female software developer"
    assert outcome(builder)["score"] == before


def test_region_country_unknown_and_work_authorization_review(builder):
    result = outcome(builder, location_restrictions=["EMEA"])
    assert result["eligibility"]["status"] == "unknown"
    result = outcome(
        builder,
        description="Required skills\nPython.\nMust have work authorization and security clearance.",
    )
    assert any(
        c["code"] == "explicit_constraint_requires_review" for c in result["eligibility"]["checks"]
    )
    assert result["evidence_coverage"]["value"] < 1


def test_closed_unknown_and_stale_availability_separate_from_score(builder):
    assert outcome(builder, status="closed")["eligibility"]["excluded"]
    assert (
        outcome(builder, status="unknown", last_verified_at=None)["eligibility"]["checks"][0][
            "status"
        ]
        == "unknown"
    )
    assert (
        outcome(builder, last_verified_at=datetime(2026, 10, 20, tzinfo=UTC))["eligibility"][
            "checks"
        ][0]["code"]
        == "availability_stale"
    )


def test_experience_overlap_dates_scope_and_projects(builder):
    result = outcome(
        builder, description="Requirements\nPython.\n8 years of professional experience."
    )
    assert 0 < result["features"]["experience"]["value"] < 0.3
    assert result["features"]["experience"]["details"]["documented_years"] < 2.1
    builder["experience"][0]["end_date"] = None
    result = outcome(
        builder, description="Requirements\nPython.\n8 years of professional experience."
    )
    assert result["features"]["experience"]["value"] is None
    builder["experience"][0]["end_date"] = "2035-01-01"
    future = outcome(
        builder, description="Requirements\nPython.\n8 years of professional experience."
    )
    assert future["features"]["experience"]["value"] is None
    intervals = [
        (datetime(2020, 1, 1).date(), datetime(2022, 1, 1).date()),
        (datetime(2021, 1, 1).date(), datetime(2023, 1, 1).date()),
    ]
    assert merged_years(intervals) < 3.1
    result = outcome(builder, description="Must have workflow automation and Python.")
    assert result["features"]["experience"]["value"] is not None


def test_salary_currency_period_unknown_not_negative(builder):
    builder["preferences"].update({"minimum_salary": 60000, "currency": "USD"})
    result = outcome(
        builder, salary_min=70000, salary_max=90000, salary_currency="USD", salary_period="year"
    )
    assert any(
        c["kind"] == "annual_salary_disclosed_bound"
        for c in result["features"]["preferences"]["details"]["checks"]
    )
    result = outcome(builder, salary_min=70000, salary_currency="INR", salary_period="year")
    assert result["features"]["preferences"]["details"]["unknown"]
    result = outcome(builder, salary_min=70000, salary_currency="USD", salary_period="month")
    assert result["features"]["preferences"]["details"]["unknown"]


def test_weights_determinism_bounds_and_invalid_config(builder):
    result = outcome(builder)
    assert result == outcome(builder)
    assert 0 <= result["score"] <= 100
    assert 0 <= result["evidence_coverage"]["value"] <= 1
    weights = result["contributing_weights"]
    expected = (
        100
        * sum(weights[k] * result["features"][k]["value"] for k in weights)
        / sum(weights.values())
    )
    assert result["score"] == round(expected, 2)
    with pytest.raises(ValueError):
        RankingConfig(weights=(("required_skills", -1),))


def test_evaluation_metric_math_and_disclosure():
    result = metrics(["a", "c", "b"], {"a": 3, "b": 2, "c": 0}, 2)
    assert result["precision_at_k"] == 0.5 and result["recall_at_k"] == 0.5
    assert 0 < result["ndcg_at_k"] < 1
    assert metrics([], {"a": 0}, 3)["recall_at_k"] is None
    with pytest.raises(ValueError):
        metrics(["a", "a"], {"a": 3}, 2)
    data = json.loads(DATA.read_text())
    result = run_evaluation(data)
    assert result == run_evaluation(data)
    assert result["independent_human_review"] is False
    assert result["queries"][-1]["ranking"] == []


def prepare_candidate(candidate):
    candidate.post(P + "/profile/skills", json={"name": "Python"})
    candidate.patch(P + "/profile", json={"headline": "Software developer"})
    candidate.patch(
        P + "/profile/preferences",
        json={"target_titles": ["Software engineer"], "current_country": "India"},
    )


def test_refresh_persistence_reuse_and_own_authorization(candidate, other, seeded_jobs):
    prepare_candidate(candidate)
    job_id = seeded_jobs[0]
    assert candidate.get(P + "/matches/" + job_id).json()["state"] == "not_calculated"
    first = candidate.post(P + "/matches/refresh", json={})
    assert first.status_code == 200, first.text
    assert first.json()["calculated"] == 2
    repeated = candidate.post(P + "/matches/refresh", json={}).json()
    assert repeated["calculated"] == 0 and repeated["reused"] == 2
    items = candidate.get(P + "/matches").json()["items"]
    assert items and items[0]["ranking_version"] == CONFIG.identity
    assert other.get(P + "/matches").json()["total"] == 0
    assert other.get(P + "/matches/" + job_id).json()["state"] == "not_calculated"
    assert (
        candidate.get(P + "/jobs/" + job_id + "/match").json()["match"]["id"]
        == candidate.get(P + "/matches/" + job_id).json()["match"]["id"]
    )
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(MatchResult)) == 2
        assert db.scalar(select(func.count()).select_from(JobRequirementAnalysis)) == 2
    assert (
        candidate.post(
            P + "/matches/refresh", json={"candidate_id": other.get(P + "/auth/me").json()["id"]}
        ).status_code
        == 422
    )


def test_fingerprints_child_change_job_change_and_profile_reversion(candidate, seeded_jobs):
    prepare_candidate(candidate)
    job_id = seeded_jobs[0]
    candidate.post(P + "/matches/refresh", json={})
    original = candidate.get(P + "/matches/" + job_id).json()["match"]["id"]
    skill = candidate.post(P + "/profile/skills", json={"name": "Postgres"}).json()
    assert candidate.get(P + "/matches/" + job_id).json()["state"] == "stale"
    assert candidate.get(P + "/matches").json()["total"] == 0
    assert candidate.get(P + "/matches?include_stale=true").json()["total"] == 2
    candidate.post(P + "/matches/refresh", json={})
    candidate.delete(P + "/profile/skills/" + skill["id"])
    repeated = candidate.post(P + "/matches/refresh", json={}).json()
    assert repeated["reused"] == 2
    assert candidate.get(P + "/matches/" + job_id).json()["match"]["id"] == original
    with SessionLocal.begin() as db:
        db.get(Job, job_id).description = "Required skills\nKubernetes."
    assert candidate.get(P + "/matches/" + job_id).json()["state"] == "stale"
    assert candidate.post(P + "/matches/refresh", json={}).json()["calculated"] == 1


def test_ranking_configuration_changes_get_new_identity_and_result(
    candidate, seeded_jobs, monkeypatch
):
    import app.modules.matching.service as service

    prepare_candidate(candidate)
    candidate.post(P + "/matches/refresh", json={})
    config = RankingConfig(
        weights=(
            ("required_skills", 0.50),
            ("preferred_skills", 0.10),
            ("experience", 0.10),
            ("role", 0.15),
            ("location", 0.10),
            ("preferences", 0.05),
        )
    )
    monkeypatch.setattr(service, "CONFIG", config)
    assert candidate.get(P + "/matching/status").json()["stale_results"] == 2
    refreshed = candidate.post(P + "/matches/refresh", json={})
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["calculated"] == 2
    assert refreshed.json()["ranking_version"] != CONFIG.identity


@pytest.mark.parametrize(
    ("kind", "payload", "field", "changed"),
    [
        (
            "experience",
            {
                "employer": "TEST ONLY",
                "title": "Developer",
                "responsibilities": "Python",
                "start_date": "2020-01-01",
                "end_date": "2022-01-01",
            },
            "responsibilities",
            "Python and SQL",
        ),
        (
            "education",
            {
                "institution": "TEST ONLY",
                "qualification": "Bachelor",
                "field_of_study": "Computing",
            },
            "field_of_study",
            "Mathematics",
        ),
    ],
)
def test_child_edit_delete_revert_and_job_change_prevents_unsafe_reuse(
    candidate, seeded_jobs, kind, payload, field, changed
):
    prepare_candidate(candidate)
    original_child = candidate.post(P + "/profile/" + kind, json=payload)
    assert original_child.status_code == 201, original_child.text
    path = P + "/profile/" + kind + "/" + original_child.json()["id"]
    assert candidate.post(P + "/matches/refresh", json={}).json()["calculated"] == 2
    job_id = seeded_jobs[0]
    original = candidate.get(P + "/matches/" + job_id).json()["match"]["id"]
    assert candidate.put(path, json={**payload, field: changed}).status_code == 200
    assert candidate.get(P + "/matching/status").json()["stale_results"] == 2
    assert candidate.post(P + "/matches/refresh", json={}).json()["calculated"] == 2
    assert candidate.put(path, json=payload).status_code == 200
    assert candidate.post(P + "/matches/refresh", json={}).json()["reused"] == 2
    assert candidate.get(P + "/matches/" + job_id).json()["match"]["id"] == original
    with SessionLocal.begin() as db:
        db.get(Job, job_id).description = "Required skills\nSQL."
    assert candidate.get(P + "/matches/" + job_id).json()["state"] == "stale"
    assert candidate.post(P + "/matches/refresh", json={}).json()["calculated"] == 1
    assert candidate.delete(path).status_code == 204
    assert candidate.get(P + "/matching/status").json()["stale_results"] == 2


def test_preference_and_daily_clock_invalidation(candidate, seeded_jobs, monkeypatch):
    from datetime import timedelta

    import app.modules.matching.representations as representations

    prepare_candidate(candidate)
    candidate.post(P + "/matches/refresh", json={})
    candidate.patch(P + "/profile/preferences", json={"work_arrangements": ["hybrid"]})
    assert candidate.get(P + "/matching/status").json()["stale_results"] == 2
    candidate.post(P + "/matches/refresh", json={})
    actual_datetime = representations.datetime

    class Tomorrow(actual_datetime):
        @classmethod
        def now(cls, tz=None):
            return actual_datetime.now(tz) + timedelta(days=1)

    monkeypatch.setattr(representations, "datetime", Tomorrow)
    assert candidate.get(P + "/matching/status").json()["stale_results"] == 2


def test_bounded_refresh_pagination_filter_validation_and_ties(candidate, seeded_jobs):
    prepare_candidate(candidate)
    first = candidate.post(P + "/matches/refresh", json={"limit": 1}).json()
    assert first["has_more"] and first["status"] == "partial"
    second = candidate.post(
        P + "/matches/refresh", json={"after_job_id": first["next_job_id"]}
    ).json()
    assert not second["has_more"]
    assert candidate.get(P + "/matches?page_size=1").json()["total"] == 2
    assert candidate.get(P + "/matches?minimum_score=101").status_code == 422
    assert candidate.get(P + "/matches?required_coverage=-1").status_code == 422
    assert candidate.post(P + "/matches/refresh", json={"limit": 201}).status_code == 422
    assert (
        candidate.post(P + "/matches/refresh", json={"job_ids": [str(uuid4())]}).status_code == 404
    )
    first_order = [r["id"] for r in candidate.get(P + "/matches").json()["items"]]
    assert first_order == [r["id"] for r in candidate.get(P + "/matches").json()["items"]]


def test_not_calculated_insufficient_and_authentication(client, candidate, seeded_jobs):
    r = candidate.post(P + "/matches/refresh", json={})
    assert r.status_code == 200, r.text
    items = candidate.get(P + "/matches").json()["items"]
    assert all(item["score"] is None for item in items)
    assert all(item["assessment_status"] == "insufficient_information" for item in items)
    candidate.cookies.clear()
    for path in ["/matches", "/matching/status", "/matches/" + seeded_jobs[0]]:
        assert candidate.get(P + path).status_code == 401
    assert candidate.post(P + "/matches/refresh", json={}).status_code == 401


def test_refresh_failure_rolls_back_and_does_not_fake_current(candidate, seeded_jobs, monkeypatch):
    import app.modules.matching.service as service

    prepare_candidate(candidate)

    def fail(*args, **kwargs):
        raise OperationalError("private SQL", {}, Exception("PRIVATE"))

    monkeypatch.setattr(service, "evaluate", fail)
    r = candidate.post(P + "/matches/refresh", json={})
    assert r.status_code == 503 and "PRIVATE" not in r.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(MatchResult)) == 0
        assert db.scalar(select(func.count()).select_from(MatchingRefresh)) == 0


def test_partial_failure_keeps_previous_assessment_stale(candidate, seeded_jobs, monkeypatch):
    import app.modules.matching.service as service

    prepare_candidate(candidate)
    candidate.post(P + "/matches/refresh", json={})
    candidate.patch(P + "/profile", json={"summary": "Recorded Python project."})
    original = service.evaluate

    def partial(snapshot, job, *args, **kwargs):
        if "Python" in job["title"]:
            raise ValueError("invalid synthetic fixture")
        return original(snapshot, job, *args, **kwargs)

    monkeypatch.setattr(service, "evaluate", partial)
    r = candidate.post(P + "/matches/refresh", json={})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "partial" and r.json()["failed"] == 1
    assert candidate.get(P + "/matching/status").json()["stale_results"] == 1


def test_closed_jobs_excluded_and_source_quotes_suppressed(candidate, seeded_jobs):
    prepare_candidate(candidate)
    candidate.post(P + "/matches/refresh", json={})
    job_id = seeded_jobs[0]
    with SessionLocal.begin() as db:
        db.get(Job, job_id).status = "closed"
    assert all(
        item["job"]["id"] != job_id for item in candidate.get(P + "/matches").json()["items"]
    )
    assert candidate.get(P + "/matches/" + job_id).json()["state"] == "stale"


def test_concurrent_refresh_requests_are_idempotent(candidate, seeded_jobs):
    prepare_candidate(candidate)
    cookies = dict(candidate.cookies)

    def refresh(_):
        with TestClient(app, cookies=cookies) as c:
            return c.post(P + "/matches/refresh", json={}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(refresh, range(2)))
    assert all(s in {200, 409} for s in statuses) and 200 in statuses
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(MatchResult)) == 2
