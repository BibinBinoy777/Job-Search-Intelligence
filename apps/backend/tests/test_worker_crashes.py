"""Kill actual isolated worker processes at durable transaction boundaries."""

import os
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.security import utcnow
from app.db.models import (
    AutomationTask,
    DeliveryAttempt,
    IngestionRun,
    Job,
    JobEvent,
    JobSource,
    Notification,
    NotificationOutbox,
)
from app.db.session import SessionLocal
from app.modules.automation import worker
from app.modules.sources.contracts import SourcePage
from tests.test_automation import alert, application, optin, prepare_email, reminder
from tests.test_discovery import AdapterFixture, execute, raw_job


@pytest.fixture
def source():
    with SessionLocal.begin() as db:
        row = JobSource(
            name="TEST ONLY crash source",
            source_type="api",
            adapter_key="himalayas",
            enabled=True,
            page_limit=1,
        )
        db.add(row)
        db.flush()
        return row.id


def kill_at_marker(tmp_path, code):
    marker = tmp_path / "boundary"
    guard = "import os; assert os.environ['DATABASE_URL'].rsplit('/',1)[-1].endswith('_test'); "
    code = (
        guard
        + "from pathlib import Path; import time; marker=Path("
        + repr(str(marker))
        + ");\n"
        + code
    )
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 35
        while not marker.exists() and time.monotonic() < deadline:
            assert process.poll() is None, "Synthetic boundary worker exited before reaching marker"
            time.sleep(0.1)
        assert marker.exists(), "Actual process did not reach intended failure boundary"
    finally:
        if process.poll() is None:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                process.kill()
        process.wait(timeout=15)


def count(model):
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(model))


def expire_task():
    with SessionLocal.begin() as db:
        task = db.scalar(select(AutomationTask))
        task.lease_until = utcnow() - timedelta(seconds=1)
    worker.recover_leases()
    with SessionLocal.begin() as db:
        db.scalar(select(AutomationTask)).due_at = utcnow()


def test_real_crash_during_reminder_transaction(candidate, seeded_jobs, tmp_path):
    a = application(candidate, seeded_jobs)
    reminder(candidate, a["id"])
    kill_at_marker(
        tmp_path,
        """from app.modules.automation import worker
original=worker.process_reminder
def interrupted(db,task):
    result=original(db,task)
    marker.touch();time.sleep(999)
    return result
worker.process_reminder=interrupted
worker.process_task(worker.claim_task())
""",
    )
    assert count(Notification) == 0
    worker.background_once()
    with SessionLocal() as db:
        assert db.scalar(select(AutomationTask.status)) == "running"
    assert count(Notification) == 0
    expire_task()
    worker.background_once()
    worker.background_once()
    assert count(Notification) == 1 and count(DeliveryAttempt) == 1


def test_real_crash_during_inapp_outbox(candidate, seeded_jobs, tmp_path):
    a = application(candidate, seeded_jobs)
    reminder(candidate, a["id"])
    worker.background_once(max_deliveries=0)
    kill_at_marker(
        tmp_path,
        """from app.modules.automation import worker
original=worker.permitted_delivery
def interrupted(*args):
    allowed=original(*args)
    marker.touch();time.sleep(999)
    return allowed
worker.permitted_delivery=interrupted
worker.deliver(worker.claim_delivery())
""",
    )
    with SessionLocal.begin() as db:
        box = db.scalar(select(NotificationOutbox))
        assert box.status == "sending"
        box.lease_until = utcnow() - timedelta(seconds=1)
    worker.recover_leases()
    worker.background_once()
    worker.background_once()
    with SessionLocal() as db:
        assert db.scalar(select(NotificationOutbox.status)) == "delivered"
    assert count(Notification) == 1 and count(DeliveryAttempt) == 2


def test_real_crash_email_acceptance_held(candidate, source, tmp_path, monkeypatch):
    prepare_email(candidate, source, monkeypatch)
    kill_at_marker(
        tmp_path,
        """from app.modules.automation import worker
def uncertain_sender(*args):
    marker.touch();time.sleep(999)
worker.deliver(worker.claim_delivery(),sender=uncertain_sender)
""",
    )
    with SessionLocal.begin() as db:
        box = db.scalar(select(NotificationOutbox).where(NotificationOutbox.channel == "email"))
        box.lease_until = utcnow() - timedelta(seconds=1)
    worker.recover_leases()
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(NotificationOutbox.status).where(NotificationOutbox.channel == "email")
            )
            == "uncertain"
        )
    assert worker.claim_delivery() is None


def test_real_crash_after_event_commit(candidate, source, tmp_path):
    optin(candidate)
    alert(candidate)
    kill_at_marker(
        tmp_path,
        """from app.db.session import SessionLocal
from app.ingestion.persistence import persist_observation
from app.modules.sources.normalization import normalize_himalayas
from app.modules.sources.contracts import Verification
from app.core.security import utcnow
from tests.test_discovery import raw_job
with SessionLocal.begin() as db:
    persist_observation(db,normalize_himalayas(raw_job(),"""
        + repr(source)
        + """),Verification('active','single_job_api_open',utcnow()))
marker.touch();time.sleep(999)
""",
    )
    assert count(Job) == count(JobEvent) == count(AutomationTask) == 1
    worker.background_once()
    worker.background_once()
    assert count(Notification) == 1
    execute(source, AdapterFixture([SourcePage([raw_job()], None)]))
    worker.background_once()
    assert count(JobEvent) == count(Notification) == 1


def test_real_crash_during_ingestion_recovers_checkpoint(source, tmp_path):
    from app.ingestion.control import queue_run
    from app.modules.automation.sources import coordinate_sources

    with SessionLocal.begin() as db:
        run = queue_run(db, source)
        key = run.id
    kill_at_marker(
        tmp_path,
        """from app.ingestion.service import process_run
from tests.test_discovery import AdapterFixture
class Interrupted(AdapterFixture):
    def fetch_jobs(self,*args,**kwargs):
        marker.touch();time.sleep(999)
process_run("""
        + repr(key)
        + """,Interrupted())
""",
    )
    with SessionLocal.begin() as db:
        run = db.get(IngestionRun, key)
        assert run.status == "running"
        run.heartbeat_at = utcnow() - timedelta(minutes=11)
    coordinate_sources()
    with SessionLocal.begin() as db:
        run = db.get(IngestionRun, key)
        assert run.status == "interrupted"
        run.retry_at = utcnow() - timedelta(seconds=1)
    coordinate_sources()
    with SessionLocal() as db:
        retry = db.scalar(select(IngestionRun).where(IngestionRun.root_run_id == key))
        rid = retry.id
    from app.ingestion.service import process_run

    assert process_run(rid, AdapterFixture())
    assert count(Job) == count(JobEvent) == 1


def test_supervisor_database_unavailable_is_not_healthy(tmp_path):
    import json

    from app.db.session import engine

    directory = tmp_path / "runtime"
    backend = Path(__file__).resolve().parents[1]
    environment = {
        **os.environ,
        "DATABASE_URL": engine.url.set(port=1).render_as_string(hide_password=False),
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "app.operations.supervisor", str(directory)],
        cwd=backend,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 45
        observed = None
        while time.monotonic() < deadline:
            try:
                value = json.loads((directory / "worker-state.json").read_text())
                if value.get("status") == "restart_backoff":
                    observed = value
                    break
            except (OSError, ValueError):
                pass
            time.sleep(0.2)
        assert observed and observed["exit_code"] != 0 and observed["restarts"] >= 1
        (directory / "worker.stop").touch()
        process.wait(timeout=30)
        assert process.returncode == 0
    finally:
        directory.mkdir(exist_ok=True)
        (directory / "worker.stop").touch()
        if process.poll() is None:
            process.wait(timeout=30)
