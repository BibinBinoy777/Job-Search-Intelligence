import io
import zipfile
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import utcnow
from app.db.models import Job, RecoveryToken, User
from app.db.session import SessionLocal
from app.operations.accounts import issue_local_recovery

P = "/api/v1/account"


def token(candidate):
    with SessionLocal.begin() as db:
        return issue_local_recovery(db, "candidate@example.com")


def test_recovery_single_use_expiry_and_revocation(candidate):
    value = token(candidate)
    body = {"token": value, "password": "NEW TEST ONLY password 8832"}
    assert candidate.post(P + "/recovery/confirm", json=body).status_code == 200
    assert candidate.get("/api/v1/auth/me").status_code == 401
    assert candidate.post(P + "/recovery/confirm", json=body).status_code == 422
    assert (
        candidate.post(
            "/api/v1/auth/login",
            json={"email": "candidate@example.com", "password": body["password"]},
        ).status_code
        == 200
    )
    expired = token(candidate)
    with SessionLocal.begin() as db:
        db.scalar(select(RecoveryToken)).expires_at = utcnow() - timedelta(seconds=1)
    assert (
        candidate.post(P + "/recovery/confirm", json={**body, "token": expired}).status_code == 422
    )


def test_recovery_request_privacy_and_throttle(candidate):
    real = candidate.post(P + "/recovery/request", json={"email": "candidate@example.com"})
    missing = candidate.post(P + "/recovery/request", json={"email": "TEST-missing@example.com"})
    assert real.json() == missing.json() and "token" not in real.text
    for _ in range(10):
        candidate.post(P + "/recovery/request", json={"email": "missing@example.com"})
    assert (
        candidate.post(P + "/recovery/request", json={"email": "missing@example.com"}).status_code
        == 429
    )


def test_password_change_invalidates_recovery_and_all_sessions(candidate):
    value = token(candidate)
    r = candidate.post(
        P + "/password",
        json={
            "current_password": "Test-password-827!",
            "new_password": "NEW TEST ONLY password 123",
        },
    )
    assert r.status_code == 200
    assert candidate.get("/api/v1/auth/me").status_code == 401
    assert (
        candidate.post(
            P + "/recovery/confirm", json={"token": value, "password": "NEW TEST ONLY password 456"}
        ).status_code
        == 422
    )


def test_local_recovery_disabled_in_production(candidate, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    from fastapi import HTTPException

    with SessionLocal.begin() as db:
        with pytest.raises(HTTPException):
            issue_local_recovery(db, "candidate@example.com")


def test_export_ownership_and_delete_confirmation(candidate, other, seeded_jobs):
    candidate.patch("/api/v1/profile", json={"summary": "TEST ONLY owner private"})
    other.patch("/api/v1/profile", json={"summary": "TEST ONLY other private"})
    candidate.post("/api/v1/applications", json={"job_id": seeded_jobs[0]})
    response = candidate.get(P + "/export")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        body = archive.read("account.json").decode()
        assert "TEST ONLY owner private" in body and "TEST ONLY other private" not in body
        assert "password_hash" not in body and "token_hash" not in body
    assert (
        candidate.post(
            P + "/deletion/confirm", json={"password": "Test-password-827!", "confirmation": "no"}
        ).status_code
        == 403
    )
    assert candidate.get("/api/v1/auth/me").status_code == 200
    result = candidate.post(
        P + "/deletion/confirm",
        json={"password": "Test-password-827!", "confirmation": "DELETE MY ACCOUNT"},
    )
    assert result.status_code == 200 and result.json()["status"] == "deleted"
    assert candidate.get("/api/v1/auth/me").status_code == 401
    assert other.get("/api/v1/auth/me").status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(User).where(User.email == "candidate@example.com")) is None
        assert len(db.scalars(select(Job)).all()) == 2


def test_revoke_all_and_operator_health_scope(candidate):
    assert candidate.get(P + "/sessions").json()["sessions"]
    assert "token_hash" not in candidate.get(P + "/sessions").text
    assert candidate.get("/api/v1/operations/health").status_code == 403
    with SessionLocal.begin() as db:
        db.scalar(select(User)).is_operator = True
    r = candidate.get("/api/v1/operations/health")
    assert r.status_code == 200
    assert r.json()["database"] == "available" and r.json()["malware_scanning"] == "not_configured"
    assert candidate.delete(P + "/sessions").status_code == 200
    assert candidate.get("/api/v1/auth/me").status_code == 401
    assert candidate.get(P + "/export").status_code == 401


def test_resume_export_and_pending_deletion_retry(candidate, tmp_path, monkeypatch):
    from app.db.models import ResumeVersion
    from app.modules.resumes.storage import PrivateStorage
    from tests.test_resumes import upload

    monkeypatch.setattr(settings, "resume_storage_root", tmp_path / "private")
    result = upload(candidate)
    assert result.status_code == 201
    exported = candidate.get(P + "/export")
    with zipfile.ZipFile(io.BytesIO(exported.content)) as z:
        assert any(n.startswith("resumes/") for n in z.namelist())
    uid = candidate.get("/api/v1/auth/me").json()["id"]
    from app.operations.accounts import delete_account

    original = PrivateStorage.delete

    def failed(*a):
        raise OSError("TEST ONLY storage failure")

    monkeypatch.setattr(PrivateStorage, "delete", failed)
    response = candidate.post(
        P + "/deletion/confirm",
        json={"password": "Test-password-827!", "confirmation": "DELETE MY ACCOUNT"},
    )
    assert response.status_code == 202 and response.json()["status"] == "deletion_pending"
    assert candidate.get("/api/v1/auth/me").status_code == 401
    with SessionLocal() as db:
        assert db.get(User, uid).deletion_pending
    monkeypatch.setattr(PrivateStorage, "delete", original)
    with SessionLocal() as db:
        assert delete_account(db, uid)["status"] == "deleted"
        db.commit()
    with SessionLocal() as db:
        assert db.get(User, uid) is None and not db.scalars(select(ResumeVersion)).all()
    assert not list((tmp_path / "private").rglob("*.blob"))
