from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError

from app.api.schemas import JobIn
from app.core.security import utcnow
from app.db.models import Job, JobSource, MatchResult, SavedSearch
from app.db.session import SessionLocal, engine
from app.modules.search.schemas import normalize_query
from app.services.jobs import store_job

P = "/api/v1"


@pytest.fixture
def search_jobs():
    with SessionLocal.begin() as db:
        source = JobSource(name="TEST ONLY Search Source", source_type="manual")
        db.add(source)
        db.flush()
        specs = [
            dict(
                title="Data Analyst",
                employer="Acme Research",
                description="Required skills\nPython and SQL.\nPreferred skills\nPostgres.",
                location="Kochi",
                work_arrangement="remote",
                employment_type="full_time",
                salary_min=60000,
                salary_max=80000,
                salary_currency="USD",
                salary_period="year",
                published_at=utcnow() - timedelta(days=1),
                last_verified_at=utcnow(),
                experience_min=2,
                experience_max=4,
                skills=[
                    {"name": "Python", "kind": "required"},
                    {"name": "Postgres", "kind": "preferred"},
                ],
            ),
            dict(
                title="Research Assistant",
                employer="Acme Research",
                description="Work with a data analyst using Python and SQL.",
                location="Kochi",
                work_arrangement="remote",
                employment_type="contract",
                salary_min=5000,
                salary_currency="USD",
                salary_period="month",
            ),
            dict(
                title="Data Analyst",
                employer="Beacon",
                description="Use SQL.",
                location=None,
                work_arrangement=None,
                employment_type=None,
            ),
            dict(
                title="Senior Developer",
                employer="Beacon",
                description="Responsibilities include data analytics.",
                responsibilities="Workflow automation with Python",
                location="London",
                work_arrangement="hybrid",
                status="closed",
                salary_min=70000,
                salary_currency="GBP",
                salary_period="year",
            ),
        ]
        ids = []
        for spec in specs:
            item = store_job(db, JobIn(source_id=source.id, **spec))
            item.location_restrictions = ["India"] if spec.get("location") == "Kochi" else None
            ids.append(item.id)
        return ids


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  DATA   Analyst ", "data analyst"),
        ("Data—Analyst!", "data analyst"),
        ('"data analyst"', "data analyst"),
        ("C++ / C#", "c++ c#"),
        ("Ｐｙｔｈｏｎ", "python"),
        ("%_", "_"),
    ],
)
def test_normalization(raw, expected):
    assert normalize_query(raw) == expected


def results(candidate, **params):
    response = candidate.get(P + "/jobs", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_lexical_priority_all_terms_fields_and_empty(candidate, search_jobs):
    ids = search_jobs
    found = results(candidate, q="  DATA—Analyst! ", sort="text_relevance")
    assert found["total"] == 3
    assert {x["id"] for x in found["items"][:2]} == {ids[0], ids[2]}
    assert found["items"][2]["id"] == ids[1]
    assert found["text_relevance"][ids[0]] > found["text_relevance"][ids[1]]
    assert results(candidate, q="Acme Python")["total"] == 2
    assert results(candidate, q="workflow automation")["items"][0]["id"] == ids[3]
    assert results(candidate, q="postgr")["items"][0]["id"] == ids[0]
    assert results(candidate, q="")["total"] == 4
    assert results(candidate, q="NoSuchGenuineTerm")["total"] == 0


def test_combined_filters_or_within_groups_and_unknown(candidate, search_jobs):
    first = results(
        candidate,
        q="data analyst",
        location="Koch",
        country="India",
        work_arrangement="remote",
        employment_type="full_time",
        employer="Acme",
        skills="Python",
        experience_min=1,
        experience_max=3,
    )
    assert [j["id"] for j in first["items"]] == [search_jobs[0]]
    assert results(candidate, work_arrangement="on_site")["total"] == 0
    assert results(candidate, q="Data", country="EMEA")["total"] == 0
    assert results(candidate, q="Data", location="Kochi", work_arrangement="hybrid")["total"] == 0
    assert results(candidate, employment_types=["full_time", "contract"])["total"] == 2
    assert results(candidate, work_arrangements=["remote", "hybrid"])["total"] == 3


def test_salary_units_dates_and_null_sorts(candidate, search_jobs):
    assert (
        results(candidate, salary_min=55000, salary_currency="USD", salary_period="year")["total"]
        == 1
    )
    assert (
        results(candidate, salary_min=55000, salary_currency="USD", salary_period="month")["total"]
        == 0
    )
    assert (
        results(candidate, salary_min=55000, salary_currency="INR", salary_period="year")["total"]
        == 0
    )
    assert (
        results(candidate, published_after=(utcnow() - timedelta(days=2)).isoformat())["total"] == 1
    )
    assert (
        results(candidate, verified_after=(utcnow() - timedelta(days=1)).isoformat())["total"] == 1
    )
    assert results(candidate, sort="published_desc")["items"][0]["id"] == search_jobs[0]
    assert results(candidate, sort="verified_desc")["items"][0]["id"] == search_jobs[0]


@pytest.mark.parametrize(
    "query",
    [
        "q=" + "x" * 201,
        "q=" + "a+" * 13,
        "sort=fabricated",
        "page=0",
        "page=10001",
        "page_size=101",
        "salary_min=1",
        "salary_min=9&salary_max=1&salary_currency=USD&salary_period=year",
        "minimum_score=101",
        "required_coverage=-1",
        "experience_max=100",
        "published_after=2026-01-01",
        "candidate_id=private",
    ],
)
def test_invalid_search(candidate, query):
    assert candidate.get(P + "/jobs?" + query).status_code == 422


def test_stable_pagination_ties_and_all_sort_orders(candidate, search_jobs):
    for sort in [
        "text_relevance",
        "candidate_match",
        "recent",
        "title",
        "employer",
        "published_desc",
        "verified_desc",
    ]:
        all_ids = [j["id"] for j in results(candidate, sort=sort)["items"]]
        pages = [
            results(candidate, sort=sort, page_size=1, page=p)["items"][0]["id"]
            for p in range(1, 5)
        ]
        assert pages == all_ids
        assert all_ids == [j["id"] for j in results(candidate, sort=sort)["items"]]


def test_current_candidate_match_filters_stale_reversion_and_context(candidate, other, search_jobs):
    candidate.post(P + "/profile/skills", json={"name": "Python"})
    candidate.patch(P + "/profile", json={"headline": "Data Analyst"})
    assert results(candidate, match_state="missing")["total"] == 4
    assert candidate.post(P + "/matches/refresh", json={}).status_code == 200
    found = results(candidate, minimum_score=0, sort="candidate_match")
    assert found["total"] == 3
    assert all(
        v["state"] == "current" and v["score"] is not None for v in found["assessments"].values()
    )
    assert results(candidate, required_coverage=1)["total"] == 0
    assert results(candidate, required_coverage=0.5)["total"] == 1
    assert results(other, minimum_score=0)["total"] == 0
    skill = candidate.post(P + "/profile/skills", json={"name": "SQL"}).json()
    assert results(candidate, minimum_score=0)["total"] == 0
    assert results(candidate, match_state="stale")["total"] == 3
    candidate.delete(P + "/profile/skills/" + skill["id"])
    assert results(candidate, minimum_score=0)["total"] == 3
    with SessionLocal.begin() as db:
        db.get(Job, search_jobs[0]).description = "Must know Java."
    assert results(candidate, minimum_score=0)["total"] == 2
    assert results(candidate)["assessments"][search_jobs[0]]["score"] is None
    assert candidate.post(P + "/matches/refresh", json={}).json()["calculated"] == 1
    assert results(candidate, minimum_score=0)["total"] == 3
    with SessionLocal.begin() as db:
        record = db.scalar(select(MatchResult).where(MatchResult.job_id == search_jobs[1]))
        record.job_context = None
    assert results(candidate, minimum_score=0)["total"] == 2
    assert candidate.post(P + "/matches/refresh", json={}).json()["reused"] == 3
    assert results(candidate, minimum_score=0)["total"] == 3


def test_insufficient_is_not_zero(candidate, search_jobs):
    candidate.post(P + "/matches/refresh", json={})
    assert results(candidate, match_state="insufficient")["total"] == 3
    assert results(candidate, minimum_score=0)["total"] == 0


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "experience",
            {"employer": "TEST ONLY", "title": "Analyst", "responsibilities": "SQL analysis"},
        ),
        (
            "education",
            {
                "institution": "TEST ONLY",
                "qualification": "Bachelor",
                "field_of_study": "Computing",
            },
        ),
        ("preferences", {"work_arrangements": ["remote"]}),
        ("", {"projects": ["TEST ONLY Python prototype"]}),
    ],
)
def test_search_currentness_includes_candidate_children(candidate, search_jobs, path, payload):
    candidate.post(P + "/profile/skills", json={"name": "Python"})
    candidate.patch(P + "/profile", json={"headline": "Data Analyst"})
    candidate.post(P + "/matches/refresh", json={})
    assert results(candidate, minimum_score=0)["total"] == 3
    method = candidate.patch if path in {"", "preferences"} else candidate.post
    response = method(P + "/profile" + ("/" + path if path else ""), json=payload)
    assert response.status_code in {200, 201}, response.text
    assert results(candidate, minimum_score=0)["total"] == 0
    assert results(candidate, match_state="stale")["total"] == 3


def test_search_currentness_day_availability_and_configuration(candidate, search_jobs, monkeypatch):
    import app.modules.search.query as query_module
    from app.modules.matching.config import RankingConfig

    candidate.post(P + "/profile/skills", json={"name": "Python"})
    candidate.patch(P + "/profile", json={"headline": "Data Analyst"})
    candidate.post(P + "/matches/refresh", json={})
    assert results(candidate, minimum_score=0)["total"] == 3
    with SessionLocal.begin() as db:
        record = db.scalar(select(MatchResult).where(MatchResult.job_id == search_jobs[0]))
        day = record.assessment_day
        record.assessment_day = day - timedelta(days=1)
    assert results(candidate, minimum_score=0)["total"] == 2
    with SessionLocal.begin() as db:
        record = db.scalar(select(MatchResult).where(MatchResult.job_id == search_jobs[0]))
        record.assessment_day = day
        job = db.get(Job, search_jobs[0])
        verified = job.last_verified_at
        job.last_verified_at = verified + timedelta(seconds=1)
    assert results(candidate, minimum_score=0)["total"] == 2
    with SessionLocal.begin() as db:
        db.get(Job, search_jobs[0]).last_verified_at = verified
    assert results(candidate, minimum_score=0)["total"] == 3
    monkeypatch.setattr(query_module, "CONFIG", RankingConfig(version="TEST ONLY different policy"))
    assert results(candidate, minimum_score=0)["total"] == 0


def test_explicit_historical_view_retains_freshness_redaction(candidate, search_jobs):
    with SessionLocal.begin() as db:
        source = JobSource(name="TEST ONLY Network", source_type="api", adapter_key="himalayas")
        db.add(source)
        db.flush()
        job = db.get(Job, search_jobs[0])
        job.source_id = source.id
        job.status = "active"
        job.last_verified_at = utcnow() - timedelta(days=2)
    assert search_jobs[0] not in [j["id"] for j in results(candidate)["items"]]
    old = results(candidate, availability_scope="all", title="Data Analyst")
    job = next(j for j in old["items"] if j["id"] == search_jobs[0])
    assert (
        not job["is_available"]
        and job["source_url"] is None
        and "requires a fresh" in job["description"]
    )
    assert results(candidate, availability_scope="all", skills="Postgres")["total"] == 0
    assert (
        results(candidate, availability_scope="requires_verification", title="Data Analyst")[
            "total"
        ]
        == 2
    )
    with SessionLocal.begin() as db:
        db.get(Job, search_jobs[0]).source_expires_at = utcnow() - timedelta(hours=1)
    assert search_jobs[0] not in [
        j["id"] for j in results(candidate, availability_scope="all", status="active")["items"]
    ]
    expired = results(candidate, availability_scope="all", status="expired")["items"]
    assert [j["id"] for j in expired] == [search_jobs[0]]
    assert expired[0]["status"] == "expired"


def test_suggestions_compare_and_ownership(client, candidate, other, search_jobs):
    suggestions = candidate.get(P + "/jobs/suggestions?q=Acme").json()
    assert {s["value"] for s in suggestions["items"]} == {"Acme Research"}
    assert candidate.get(P + "/jobs/suggestions?q=Pyth").json()["items"] == [
        {"kind": "skill", "value": "Python"}
    ]
    assert candidate.get(P + "/jobs/suggestions?q=a").json()["items"] == []
    assert candidate.get(P + "/jobs/suggestions?limit=13").status_code == 422
    candidate.post(P + "/profile/skills", json={"name": "Python"})
    candidate.post(P + "/matches/refresh", json={})
    compared = candidate.post(P + "/jobs/compare", json={"job_ids": search_jobs[:3]})
    assert compared.status_code == 200, compared.text
    assert compared.json()["items"][0]["candidate_assessment"]["state"] == "current"
    assert (
        other.post(P + "/jobs/compare", json={"job_ids": search_jobs[:2]}).json()["items"][0][
            "candidate_assessment"
        ]["state"]
        == "not_calculated"
    )
    assert candidate.post(P + "/jobs/compare", json={"job_ids": search_jobs}).status_code == 422
    assert (
        candidate.post(P + "/jobs/compare", json={"job_ids": [search_jobs[0]] * 2}).status_code
        == 422
    )
    assert candidate.post(P + "/jobs/compare", json={"job_ids": [str(uuid4())]}).status_code == 404
    candidate.cookies.clear()
    assert candidate.post(P + "/jobs/compare", json={"job_ids": search_jobs[:2]}).status_code == 401
    assert candidate.get(P + "/jobs/suggestions?q=data").status_code == 401


def test_saved_search_crud_validation_ownership_and_unique(candidate, other):
    response = candidate.post(
        P + "/saved-searches",
        json={
            "name": "Remote data",
            "criteria": {
                "q": " Data  Analyst ",
                "work_arrangement": "remote",
                "sort": "text_relevance",
            },
        },
    )
    assert response.status_code == 201, response.text
    item = response.json()
    path = P + "/saved-searches/" + item["id"]
    assert item["criteria"]["q"] == "data analyst"
    assert candidate.get(P + "/saved-searches").json()["total"] == 1
    assert other.get(P + "/saved-searches").json()["total"] == 0
    for method, url, body in [
        ("patch", path, {"name": "Stolen"}),
        ("post", path + "/use", {}),
        ("delete", path, None),
    ]:
        assert (
            getattr(other, method)(url, **({"json": body} if body is not None else {})).status_code
            == 404
        )
    assert (
        candidate.patch(
            path, json={"name": "Updated", "criteria": {"employer": "Acme"}}
        ).status_code
        == 200
    )
    assert candidate.post(path + "/use").json()["last_used_at"] is not None
    assert candidate.patch(path, json={"criteria": {"password": "private"}}).status_code == 422
    assert candidate.patch(path, json={"name": None}).status_code == 422
    assert (
        candidate.post(P + "/saved-searches", json={"name": "UPDATED", "criteria": {}}).status_code
        == 409
    )
    with SessionLocal() as db:
        existing = db.scalar(select(SavedSearch))
        with pytest.raises(IntegrityError):
            db.add(
                SavedSearch(
                    profile_id=existing.profile_id,
                    name="Updated",
                    normalized_name="updated",
                    criteria={},
                )
            )
            db.flush()
        db.rollback()
    assert candidate.delete(path).status_code == 204
    assert candidate.get(P + "/saved-searches").json()["total"] == 0


def test_bounded_result_query_count(candidate, search_jobs):
    statements = []

    def trace(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", trace)
    try:
        one = results(candidate, page_size=1)
        count_one = len(statements)
        statements.clear()
        all_results = results(candidate, page_size=100)
        assert len(statements) <= count_one + 1
        assert one["total"] == all_results["total"] == 4
        assert any("LIMIT" in statement for statement in statements)
    finally:
        event.remove(engine, "before_cursor_execute", trace)


def test_saved_search_quota_and_bounded_names(candidate, other):
    profile_id = candidate.get(P + "/profile").json()["id"]
    with SessionLocal.begin() as db:
        db.add_all(
            [
                SavedSearch(
                    profile_id=profile_id,
                    name=f"TEST ONLY {i}",
                    normalized_name=f"test only {i}",
                    criteria={},
                )
                for i in range(50)
            ]
        )
    assert (
        candidate.post(P + "/saved-searches", json={"name": "Overflow", "criteria": {}}).status_code
        == 409
    )
    assert candidate.get(P + "/saved-searches?page_size=100").json()["total"] == 50
    assert candidate.get(P + "/saved-searches?page=10001").status_code == 422
    assert (
        other.post(P + "/saved-searches", json={"name": "Independent", "criteria": {}}).status_code
        == 201
    )
    assert (
        other.post(P + "/saved-searches", json={"name": "ß" * 100, "criteria": {}}).status_code
        == 422
    )
