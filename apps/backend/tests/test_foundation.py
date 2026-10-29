from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from conftest import signup
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.api.schemas import JobIn
from app.core.config import Settings
from app.core.security import utcnow
from app.db.models import Application, ApplicationEvent, AuthSession, Job, Profile, User
from app.db.session import SessionLocal, engine
from app.main import app
from app.services.jobs import store_job

P = "/api/v1"


def test_health_and_openapi(client):
    assert client.get(P + "/health/live").json() == {"status": "ok"}
    assert client.get(P + "/health/ready").status_code == 200
    assert "/api/v1/profile" in client.get("/openapi.json").json()["paths"]


def test_authentication_is_required(client):
    for path in ["/profile", "/jobs", "/saved-jobs", "/applications", "/overview", "/sources"]:
        assert client.get(P + path).status_code == 401
    assert client.get(P + "/profile", headers={"X-User-ID": str(uuid4())}).status_code == 401


def test_register_login_logout_cookie_and_private_password(client):
    response = client.post(
        P + "/auth/register", json={"email": "PERSON@example.com", "password": "Test-password-827!"}
    )
    assert response.status_code == 201
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    token = client.cookies.get("jsi_session")
    assert "password" not in response.text
    with SessionLocal() as db:
        user = db.scalar(select(User))
        assert user.password_hash.startswith("$argon2")
        assert db.scalar(select(AuthSession.token_hash)) != token
    assert client.get(P + "/auth/me").json()["email"] == "person@example.com"
    assert client.post(P + "/auth/logout").status_code == 204
    assert client.get(P + "/auth/me").status_code == 401
    client.cookies.set("jsi_session", token)
    assert client.get(P + "/auth/me").status_code == 401
    client.cookies.clear()
    assert (
        client.post(
            P + "/auth/login",
            json={"email": "person@example.com", "password": "Wrong-password-827!"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            P + "/auth/login",
            json={"email": "person@example.com", "password": "Test-password-827!"},
        ).status_code
        == 200
    )


def test_expired_session(candidate):
    with SessionLocal.begin() as db:
        session = db.scalar(select(AuthSession))
        session.expires_at = utcnow() - timedelta(seconds=1)
    assert candidate.get(P + "/profile").status_code == 401


def test_origin_protection_and_auth_throttle(client):
    assert (
        client.post(
            P + "/auth/login", json={}, headers={"Origin": "https://untrusted.example"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            P + "/auth/login", json={}, headers={"Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )
    for _ in range(12):
        assert (
            client.post(
                P + "/auth/login",
                json={"email": "none@example.com", "password": "Wrong-password-827!"},
            ).status_code
            == 401
        )
    assert (
        client.post(
            P + "/auth/login", json={"email": "none@example.com", "password": "Wrong-password-827!"}
        ).status_code
        == 429
    )


def test_validation_redacts_passwords(client):
    r = client.post(P + "/auth/register", json={"email": "bad", "password": "SHORT_SECRET"})
    assert r.status_code == 422
    assert "SHORT_SECRET" not in r.text and "input" not in r.text


def test_production_configuration_fails_closed():
    with pytest.raises(ValueError):
        Settings(app_env="production", cookie_secure=False)
    with pytest.raises(ValueError):
        Settings(database_url="sqlite:///fake.db")


def test_profile_create_read_update_and_unknown(client):
    signup(client, profile=False)
    assert client.get(P + "/profile").status_code == 404
    created = client.post(P + "/profile", json={})
    assert created.status_code == 201
    assert created.json()["name"] is None
    assert client.post(P + "/profile", json={}).status_code == 409
    result = client.patch(
        P + "/profile",
        json={"name": "New Name", "headline": "Builder", "projects": ["Project one"]},
    )
    assert result.status_code == 200
    assert client.get(P + "/profile").json()["projects"] == ["Project one"]


def test_skills_idempotency_ownership_and_delete(candidate, other):
    r = candidate.post(P + "/profile/skills", json={"name": "Python"})
    assert r.status_code == 200
    assert (
        candidate.post(P + "/profile/skills", json={"name": "python"}).json()["id"]
        == r.json()["id"]
    )
    assert len(candidate.get(P + "/profile/skills").json()) == 1
    assert other.get(P + "/profile/skills").json() == []
    assert other.delete(P + "/profile/skills/" + r.json()["id"]).status_code == 404
    assert candidate.delete(P + "/profile/skills/" + r.json()["id"]).status_code == 204
    assert candidate.get(P + "/profile/skills").json() == []


@pytest.mark.parametrize(
    ("kind", "data"),
    [
        (
            "experience",
            {
                "employer": "Test",
                "title": "Developer",
                "start_date": "2024-01-01",
                "end_date": "2025-01-01",
                "responsibilities": "Build",
                "achievements": "Delivered",
                "technologies": ["Python"],
            },
        ),
        (
            "education",
            {
                "institution": "Test Institute",
                "qualification": "BTech",
                "field_of_study": "CS",
                "start_date": "2020-01-01",
                "end_date": "2024-01-01",
            },
        ),
    ],
)
def test_history_crud_ownership_and_dates(candidate, other, kind, data):
    assert (
        candidate.post(P + "/profile/" + kind, json={**data, "end_date": "2010-01-01"}).status_code
        == 422
    )
    r = candidate.post(P + "/profile/" + kind, json=data)
    assert r.status_code == 201
    item_id = r.json()["id"]
    assert other.put(P + f"/profile/{kind}/{item_id}", json=data).status_code == 404
    assert other.delete(P + f"/profile/{kind}/{item_id}").status_code == 404
    assert (
        candidate.put(P + f"/profile/{kind}/{item_id}", json={**data, "end_date": None}).status_code
        == 200
    )
    assert len(candidate.get(P + "/profile/" + kind).json()) == 1
    assert candidate.delete(P + f"/profile/{kind}/{item_id}").status_code == 204


def test_preferences_validation_and_profile_ownership(candidate, other):
    r = candidate.patch(
        P + "/profile/preferences",
        json={
            "target_titles": ["AI Builder"],
            "minimum_salary": 500000,
            "currency": "INR",
            "relocation": False,
        },
    )
    assert r.status_code == 200
    assert candidate.get(P + "/profile").json()["preferences"]["relocation"] is False
    assert other.get(P + "/profile/preferences").json()["target_titles"] == []
    assert candidate.patch(P + "/profile/preferences", json={"currency": None}).status_code == 422
    assert (
        candidate.patch(
            P + "/profile/preferences", json={"work_arrangements": ["telepathy"]}
        ).status_code
        == 422
    )
    assert (
        candidate.patch(
            P + "/profile", json={"user_id": other.get(P + "/auth/me").json()["id"]}
        ).status_code
        == 422
    )


def test_job_search_filters_and_pagination(candidate, seeded_jobs):
    a, b, source = seeded_jobs
    for query in [
        "q=Python",
        "q=FastAPI",
        "location=Kochi",
        "work_arrangement=remote",
        "employment_type=full_time",
    ]:
        r = candidate.get(P + "/jobs?" + query)
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 1
        assert r.json()["items"][0]["id"] == a
    assert candidate.get(P + "/jobs?source_id=" + source).json()["total"] == 2
    page = candidate.get(P + "/jobs?page_size=1&page=2").json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert candidate.get(P + "/jobs?page=0").status_code == 422
    assert candidate.get(P + "/jobs?work_arrangement=bogus").status_code == 422
    assert candidate.get(P + "/jobs/not-a-uuid").status_code == 422
    assert candidate.get(P + "/jobs/" + str(uuid4())).status_code == 404
    assert candidate.get(P + "/jobs/" + b).json()["last_verified_at"] is None


def test_job_validation_source_identity_and_material_updates(candidate, seeded_jobs):
    a, _, source = seeded_jobs
    with SessionLocal.begin() as db:
        first = db.get(Job, a)
        seen = first.first_seen_at
        material = first.material_updated_at
        payload = JobIn.model_validate(first)
        repeated = store_job(db, payload)
        assert repeated.id == a and repeated.first_seen_at == seen
        assert repeated.material_updated_at == material
        payload.title = "TEST ONLY Revised role"
        revised = store_job(db, payload)
        assert revised.material_updated_at >= material
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 2
    with pytest.raises(ValueError):
        JobIn(title="", employer="TEST", description="TEST")
    with pytest.raises(ValueError):
        JobIn(title="TEST", employer="TEST", description="TEST", external_id="orphan")
    with pytest.raises(ValueError):
        JobIn(
            title="TEST",
            employer="TEST",
            description="TEST",
            salary_min=100,
            salary_max=1,
            salary_currency="INR",
        )
    with SessionLocal() as db:
        db.add(
            Job(
                source_id=source,
                external_id="fixture-a",
                title="duplicate",
                employer="TEST",
                description="TEST",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_unknown_source_identity_does_not_merge_titles(seeded_jobs):
    _, _, source = seeded_jobs
    with SessionLocal.begin() as db:
        data = JobIn(
            title="Same title TEST ONLY", employer="TEST", description="TEST", source_id=source
        )
        assert store_job(db, data).id != store_job(db, data).id


def test_concurrent_source_delivery_is_idempotent(seeded_jobs):
    _, _, source = seeded_jobs

    def deliver(_):
        with SessionLocal.begin() as db:
            return store_job(
                db,
                JobIn(
                    title="Concurrent TEST ONLY",
                    employer="TEST",
                    description="TEST",
                    source_id=source,
                    external_id="concurrent",
                ),
            ).id

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len(set(pool.map(deliver, range(4)))) == 1


def test_saved_jobs_are_persistent_idempotent_and_private(candidate, other, seeded_jobs):
    a, _, _ = seeded_jobs
    for _ in range(2):
        assert candidate.put(P + f"/jobs/{a}/save").status_code == 200
    assert candidate.get(P + "/saved-jobs").json()["total"] == 1
    assert candidate.get(P + f"/jobs/{a}").json()["is_saved"] is True
    assert other.get(P + "/saved-jobs").json()["total"] == 0
    assert other.delete(P + f"/jobs/{a}/save").status_code == 204
    assert candidate.get(P + "/saved-jobs").json()["total"] == 1
    assert candidate.delete(P + f"/jobs/{a}/save").status_code == 204
    assert candidate.get(P + "/saved-jobs").json()["total"] == 0
    assert candidate.put(P + f"/jobs/{uuid4()}/save").status_code == 404


def test_concurrent_saving(candidate, seeded_jobs):
    a, _, _ = seeded_jobs
    cookies = dict(candidate.cookies)

    def save(_):
        with TestClient(app, cookies=cookies) as c:
            return c.put(P + f"/jobs/{a}/save").status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(save, range(4))) == [200] * 4
    assert candidate.get(P + "/saved-jobs").json()["total"] == 1


def test_application_lifecycle_history_and_ownership(candidate, other, seeded_jobs):
    a, _, _ = seeded_jobs
    r = candidate.post(P + "/applications", json={"job_id": a, "notes": "My notes"})
    assert r.status_code == 201, r.text
    item = r.json()
    item_id = item["id"]
    assert candidate.post(P + "/applications", json={"job_id": a}).status_code == 409
    for suffix in ["", "/events"]:
        assert other.get(P + f"/applications/{item_id}" + suffix).status_code == 404
    assert (
        other.patch(
            P + f"/applications/{item_id}", json={"expected_version": 1, "status": "applied"}
        ).status_code
        == 404
    )
    assert other.get(P + "/applications").json()["total"] == 0
    changed = candidate.patch(
        P + f"/applications/{item_id}",
        json={"expected_version": item["version"], "status": "applied", "applied_on": "2026-10-01"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["version"] == 2
    assert (
        candidate.patch(
            P + f"/applications/{item_id}", json={"expected_version": 1, "status": "interview"}
        ).status_code
        == 409
    )
    events = candidate.get(P + f"/applications/{item_id}/events").json()
    assert [e["to_status"] for e in events["items"]] == ["interested", "applied"]
    with SessionLocal() as db:
        assert db.get(Application, item_id).status == "applied"
        assert (
            db.scalar(
                select(func.count())
                .select_from(ApplicationEvent)
                .where(ApplicationEvent.application_id == item_id)
            )
            == 2
        )
    assert candidate.get(P + "/overview").json()["application_count"] == 1


def test_application_corrections_and_invalid_values(candidate, seeded_jobs):
    a, _, _ = seeded_jobs
    item = candidate.post(P + "/applications", json={"job_id": a, "status": "rejected"}).json()
    path = P + "/applications/" + item["id"]
    assert (
        candidate.patch(path, json={"expected_version": 1, "status": "interview"}).status_code
        == 422
    )
    r = candidate.patch(
        path,
        json={
            "expected_version": 1,
            "status": "interview",
            "correction_reason": "Outcome entered incorrectly",
        },
    )
    assert r.status_code == 200, r.text
    assert (
        candidate.get(path + "/events").json()["items"][-1]["reason"]
        == "Outcome entered incorrectly"
    )
    assert candidate.patch(path, json={"expected_version": 2, "status": None}).status_code == 422
    assert candidate.patch(path, json={"expected_version": 2, "status": "magic"}).status_code == 422
    assert (
        candidate.patch(path, json={"expected_version": 2, "applied_on": "2099-01-01"}).status_code
        == 422
    )
    assert candidate.patch(path, json={"status": "applied"}).status_code == 422
    assert candidate.get(P + "/applications/" + str(uuid4())).status_code == 404


def test_failed_event_write_rolls_back_status(candidate, seeded_jobs, monkeypatch):
    a, _, _ = seeded_jobs
    item = candidate.post(P + "/applications", json={"job_id": a}).json()
    from sqlalchemy.orm import Session

    original = Session.flush

    def failing_flush(self, *args, **kwargs):
        if any(isinstance(obj, ApplicationEvent) and obj.from_status for obj in self.new):
            raise OperationalError("redacted", {}, Exception("unavailable"))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Session, "flush", failing_flush)
    r = candidate.patch(
        P + "/applications/" + item["id"], json={"expected_version": 1, "status": "applied"}
    )
    assert r.status_code == 503
    monkeypatch.setattr(Session, "flush", original)
    assert candidate.get(P + "/applications/" + item["id"]).json()["status"] == "interested"
    assert candidate.get(P + "/applications/" + item["id"] + "/events").json()["total"] == 1


def test_readiness_and_safe_database_errors(client, monkeypatch):
    import app.main as main

    def unavailable(*args, **kwargs):
        raise OperationalError("private DSN", {}, Exception("SECRET"))

    monkeypatch.setattr(main.engine, "connect", unavailable)
    r = client.get(P + "/health/ready")
    assert r.status_code == 503 and "SECRET" not in r.text
    assert client.get(P + "/health/live").status_code == 200
    client.cookies.set("jsi_session", "anything")
    r = client.get(P + "/auth/me")
    assert r.status_code == 503 and "private DSN" not in r.text


def test_migration_schema_constraints():
    with engine.connect() as conn:
        tables = (
            conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
            .scalars()
            .all()
        )
        assert set(t.name for t in Profile.metadata.sorted_tables).issubset(set(tables))


def test_real_persistence_across_sessions(candidate):
    candidate.patch(P + "/profile", json={"summary": "Persisted in PostgreSQL"})
    with SessionLocal() as fresh:
        assert fresh.scalar(select(Profile.summary)) == "Persisted in PostgreSQL"


def test_concurrent_application_updates_keep_one_history(candidate, seeded_jobs):
    a, _, _ = seeded_jobs
    item = candidate.post(P + "/applications", json={"job_id": a}).json()
    cookies = dict(candidate.cookies)

    def change(status):
        with TestClient(app, cookies=cookies) as c:
            return c.patch(
                P + "/applications/" + item["id"], json={"expected_version": 1, "status": status}
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(change, ["applied", "interview"])) == [200, 409]
    assert candidate.get(P + "/applications/" + item["id"] + "/events").json()["total"] == 2


def test_commit_failure_never_returns_success(candidate, monkeypatch):
    from sqlalchemy.orm import Session

    original = Session.commit

    def failed_commit(self):
        raise OperationalError("private query", {}, Exception("private failure"))

    monkeypatch.setattr(Session, "commit", failed_commit)
    result = candidate.patch(P + "/profile", json={"headline": "Must roll back"})
    assert result.status_code == 503
    assert "private" not in result.text
    monkeypatch.setattr(Session, "commit", original)
    assert candidate.get(P + "/profile").json()["headline"] is None


def test_verification_does_not_change_material_timestamp(seeded_jobs):
    first, _, _ = seeded_jobs
    with SessionLocal.begin() as db:
        item = db.get(Job, first)
        payload = JobIn.model_validate(item)
        payload.salary_min = 102000.25
        payload.salary_currency = "INR"
        item = store_job(db, payload)
        material = item.material_updated_at
    with SessionLocal.begin() as db:
        payload = JobIn.model_validate(db.get(Job, first))
        payload.last_verified_at = utcnow()
        repeated = store_job(db, payload)
        assert repeated.material_updated_at == material
        assert repeated.last_verified_at is not None
