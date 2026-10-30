import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.models import Profile, Resume, ResumeVersion
from app.db.session import SessionLocal, engine
from app.modules.resumes.storage import PrivateStorage
from app.operations.backup import BackupError, create_backup, restore_test, verify_backup


@pytest.fixture
def binary():
    path = os.environ.get("JSI_PG_BIN")
    if not path:
        pytest.skip("Native PostgreSQL backup tests require JSI_PG_BIN")
    return Path(path)


def test_populated_backup_restore_and_tamper(candidate, seeded_jobs, tmp_path, monkeypatch, binary):
    monkeypatch.setattr(settings, "resume_storage_root", tmp_path / "private")
    storage = PrivateStorage()
    content = (Path(__file__).parent / "fixtures/resumes/TEST-ONLY.pdf").read_bytes()
    with SessionLocal.begin() as db:
        profile = db.scalar(select(Profile))
        resume = Resume(profile_id=profile.id, name="TEST ONLY recovery", version_count=1)
        db.add(resume)
        db.flush()
        ref = profile.id + "/" + resume.id + ".blob"
        storage.write(ref, content)
        db.add(
            ResumeVersion(
                resume_id=resume.id,
                number=1,
                filename="TEST-ONLY.pdf",
                storage_ref=ref,
                detected_type="pdf",
                size_bytes=len(content),
                checksum=hashlib.sha256(content).hexdigest(),
            )
        )
    result = candidate.post("/api/v1/applications", json={"job_id": seeded_jobs[0]})
    assert result.status_code == 201
    assert candidate.put("/api/v1/jobs/" + seeded_jobs[0] + "/save").status_code == 200
    assert (
        candidate.post(
            "/api/v1/saved-searches", json={"name": "TEST ONLY backup search", "criteria": {}}
        ).status_code
        == 201
    )
    assert (
        candidate.post(
            "/api/v1/alerts", json={"name": "TEST ONLY backup alert", "criteria": {}}
        ).status_code
        == 201
    )
    assert candidate.post("/api/v1/matches/refresh", json={}).status_code == 200
    app = result.json()
    assert (
        candidate.post(
            "/api/v1/reminders",
            json={
                "application_id": app["id"],
                "local_time": "2026-01-01T10:00:00",
                "timezone": "UTC",
            },
        ).status_code
        == 201
    )
    from app.modules.automation.worker import background_once

    background_once()
    target = create_backup(tmp_path / "backups", binary, engine, storage)
    manifest = verify_backup(target)
    assert len(manifest["documents"]) == 1 and not manifest["encrypted"]
    result = restore_test(target, binary)
    assert result["status"] == "verified" and result["documents"] == 1
    assert result["all_original_values_preserved"]
    (target / "documents" / ref).write_bytes(b"TEST ONLY corrupted")
    with pytest.raises(BackupError):
        verify_backup(target)


def test_backup_missing_document_fails(candidate, tmp_path, monkeypatch, binary):
    monkeypatch.setattr(settings, "resume_storage_root", tmp_path / "private")
    with SessionLocal.begin() as db:
        profile = db.scalar(select(Profile))
        resume = Resume(profile_id=profile.id, name="TEST ONLY missing", version_count=1)
        db.add(resume)
        db.flush()
        db.add(
            ResumeVersion(
                resume_id=resume.id,
                number=1,
                filename="TEST-ONLY.pdf",
                storage_ref=profile.id + "/" + resume.id + ".blob",
                detected_type="pdf",
                size_bytes=10,
                checksum="a" * 64,
            )
        )
    with pytest.raises(OSError):
        create_backup(tmp_path / "backups", binary)
    assert any((p / "FAILED").exists() for p in (tmp_path / "backups").iterdir())


def test_parser_sanitizes_environment_and_cleans_temp(monkeypatch):
    from app.modules.resumes import extraction

    original = extraction.subprocess.run
    observed = {}
    monkeypatch.setenv("DATABASE_URL", "TEST ONLY sensitive sentinel")

    def call(*a, **kw):
        observed.update(kw)
        assert "DATABASE_URL" not in kw["env"]
        assert "SMTP_PASSWORD" not in kw["env"]
        return original(*a, **kw)

    monkeypatch.setattr(extraction.subprocess, "run", call)
    content = (Path(__file__).parent / "fixtures/resumes/TEST-ONLY.pdf").read_bytes()
    result = extraction.parse_document(content, "pdf")
    assert result and not Path(observed["cwd"]).exists()


def test_actual_supervisor_restarts_and_stops(tmp_path):
    directory = tmp_path / "runtime"
    backend = Path(__file__).resolve().parents[1]
    args = [sys.executable, "-m", "app.operations.supervisor", str(directory)]
    log = (tmp_path / "supervisor-errors.txt").open("wb")
    process = subprocess.Popen(args, cwd=backend, stdout=subprocess.DEVNULL, stderr=log)

    def state(predicate):
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            try:
                value = json.loads((directory / "worker-state.json").read_text())
                if predicate(value):
                    return value
            except (OSError, ValueError):
                pass
            time.sleep(0.2)
        raise AssertionError("Supervisor did not reach expected persisted state")

    try:
        initial = state(lambda s: s.get("status") == "running_process")
        duplicate = subprocess.run(
            args, cwd=backend, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15
        )
        assert duplicate.returncode != 0
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(initial["worker_pid"]), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        else:
            os.kill(initial["worker_pid"], 9)
        restarted = state(
            lambda s: s.get("status") == "running_process" and s.get("restarts", 0) > 0
        )
        assert restarted["worker_pid"] != initial["worker_pid"]
        (directory / "worker.stop").touch()
        process.wait(timeout=45)
        assert process.returncode == 0
        assert state(lambda s: s.get("status") == "stopped")
    finally:
        (directory / "worker.stop").touch()
        if process.poll() is None:
            process.wait(timeout=45)
        log.close()


def test_windows_backup_encryption_roundtrip(tmp_path):
    if os.name != "nt":
        pytest.skip("DPAPI is Windows-only")
    from app.operations.encryption import protect

    private = b"TEST ONLY private backup bytes"
    envelope = protect(private)
    assert private not in envelope and protect(envelope, True) == private
    with pytest.raises(BackupError):
        protect(envelope[:-10], True)


def test_safe_operational_log_redaction():
    import logging

    from app.core.logging import SafeOperationalFormatter

    r = logging.LogRecord(
        "jsi", logging.ERROR, "", 1, "failed password=SECRET_RESUME_SENTINEL", (), None
    )
    r.error_category = "database_unavailable"
    output = SafeOperationalFormatter().format(r)
    assert "SECRET_RESUME_SENTINEL" not in output and "password" not in output
    assert json.loads(output)["error_category"] == "database_unavailable"


def test_backup_retention_keeps_only_known_good(tmp_path, monkeypatch):
    from app.operations import backup

    sets = []
    for i in range(3):
        folder = tmp_path / str(i)
        folder.mkdir()
        (folder / "restore-verification.json").write_text(
            json.dumps({"backup_id": str(i), "status": "verified"})
        )
        sets.append(folder)
    monkeypatch.setattr(
        backup,
        "verify_backup",
        lambda p: {
            "backup_id": p.name,
            "created_at": "2026-10-" + str(20 + int(p.name)) + "T00:00:00+00:00",
        },
    )
    result = backup.retention_plan(tmp_path, 1, 0, 0, False)
    assert result["kept_verified"] == 1 and len(result["eligible_backup_sets"]) == 2
    assert all(p.exists() for p in sets)
    backup.retention_plan(tmp_path, 1, 0, 0, True)
    assert sets[-1].exists() and not sets[0].exists()


def test_production_configuration_rejects_unsafe_modes(tmp_path):
    from app.core.config import Settings

    configuration = {
        "app_env": "production",
        "cookie_secure": True,
        "database_url": "postgresql+psycopg://TEST_ONLY:TEST_ONLY_strong_database_credential@localhost/disposable",
        "app_base_url": "https://example.test",
        "allowed_origins": ["https://example.test"],
        "trusted_hosts": ["example.test"],
        "resume_storage_root": tmp_path / "private",
    }
    assert Settings(**configuration).app_env == "production"
    for change in [
        {"debug": True},
        {"trusted_hosts": ["*"]},
        {"cookie_secure": False},
        {"database_url": "postgresql+psycopg://TEST:password@localhost/disposable"},
        {"app_base_url": "http://example.test"},
    ]:
        with pytest.raises(ValueError) as exc:
            Settings(**{**configuration, **change})
        assert configuration["database_url"] not in str(exc.value)
