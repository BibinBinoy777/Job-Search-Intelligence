"""Phase 7 synthetic fixtures run only in the guarded disposable _test database."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from test_discovery import AdapterFixture, execute, raw_job

from app.core.config import settings
from app.core.security import utcnow
from app.db.models import (
    AutomationTask,
    DeliveryAttempt,
    Job,
    JobEvent,
    JobSource,
    Notification,
    NotificationOutbox,
    User,
)
from app.db.session import SessionLocal
from app.modules.automation import worker
from app.modules.automation.email import EmailResult
from app.modules.automation.service import local_instant
from app.modules.sources.contracts import SourcePage

P = "/api/v1"


@pytest.fixture
def source():
    with SessionLocal.begin() as db:
        row = JobSource(
            name="TEST ONLY automation",
            source_type="api",
            adapter_key="himalayas",
            enabled=True,
            page_limit=1,
        )
        db.add(row)
        db.flush()
        return row.id


def count(model):
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(model))


def alert(c, name="TEST ONLY future alert", **patch):
    r = c.post(P + "/alerts", json={"name": name, "criteria": {}, **patch})
    assert r.status_code == 201, r.text
    return r.json()


def optin(c, **patch):
    r = c.put(
        P + "/notifications/preferences",
        json={
            "job_alerts": True,
            "reminders": True,
            "in_app": True,
            "email": False,
            "timezone": "Asia/Kolkata",
            **patch,
        },
    )
    assert r.status_code == 200, r.text


def ingest(source, **patch):
    return execute(source, AdapterFixture([SourcePage([raw_job(**patch)], None)]))


def application(c, jobs):
    r = c.post(P + "/applications", json={"job_id": jobs[0]})
    assert r.status_code == 201, r.text
    return r.json()


def reminder(c, appid, **patch):
    body = {
        "application_id": appid,
        "local_time": (utcnow() - timedelta(minutes=1)).replace(tzinfo=None).isoformat(),
        "timezone": "UTC",
        "kind": "follow_up",
        **patch,
    }
    r = c.post(P + "/reminders", json=body)
    assert r.status_code == 201, r.text
    return r.json(), body


def test_events_repeat_material_and_availability(source):
    ingest(source)
    assert count(JobEvent) == 1 and count(AutomationTask) == 1
    ingest(source)
    assert count(JobEvent) == 1
    ingest(source, title="TEST ONLY changed title")
    assert count(JobEvent) == 2
    with SessionLocal.begin() as db:
        db.scalar(select(Job)).last_verified_at = utcnow() - timedelta(hours=25)
    execute(
        source,
        AdapterFixture(
            [SourcePage([raw_job(title="TEST ONLY changed title")], None)], verification="closed"
        ),
    )
    with SessionLocal() as db:
        assert db.scalars(select(JobEvent.kind).order_by(JobEvent.created_at)).all() == [
            "new_listing",
            "material_update",
            "availability_change",
        ]
    assert count(AutomationTask) == 2


def test_future_only_overlap_dedup_delivery_and_read(candidate, source, other):
    ingest(source)
    optin(candidate)
    a = alert(candidate, include_updates=True)
    alert(candidate, "TEST ONLY overlap", include_updates=True)
    worker.background_once()
    assert count(Notification) == 0
    ingest(source, title="TEST ONLY eligible updated")
    worker.background_once()
    r = candidate.get(P + "/notifications").json()
    assert r["total"] == 1 and r["unread_count"] == 1
    n = r["items"][0]
    assert n["in_app_status"] == "delivered" and n["deliveries"][0]["status"] == "delivered"
    assert other.get(P + "/notifications/" + n["id"]).status_code == 404
    assert (
        candidate.patch(P + f"/notifications/{n['id']}/read", json={"read": True}).status_code
        == 200
    )
    assert candidate.get(P + "/notifications").json()["unread_count"] == 0
    assert (
        candidate.patch(P + f"/notifications/{n['id']}/read", json={"read": False}).status_code
        == 200
    )
    assert (
        candidate.post(P + "/notifications/read-batch", json={"ids": [n["id"]]}).json()[
            "marked_read"
        ]
        == 1
    )
    assert other.get(P + f"/alerts/{a['id']}/activity").status_code == 404
    ingest(source, title="TEST ONLY eligible updated")
    worker.background_once()
    assert count(Notification) == 1 and count(DeliveryAttempt) == 1


@pytest.mark.parametrize(
    "state", ["unknown", "closed", "expired", "stale_verification", "no_verification"]
)
def test_unavailable_jobs_never_alert(candidate, source, state):
    optin(candidate)
    alert(candidate)
    ingest(source)
    with SessionLocal.begin() as db:
        job = db.scalar(select(Job))
        if state == "stale_verification":
            job.last_verified_at = utcnow() - timedelta(hours=25)
        elif state == "no_verification":
            job.last_verified_at = None
        else:
            job.status = state
    worker.background_once()
    assert count(Notification) == 0


def test_missing_score_no_implicit_refresh(candidate, source):
    optin(candidate)
    alert(candidate, criteria={"minimum_score": 0, "required_coverage": 0})
    ingest(source)
    worker.background_once()
    assert count(Notification) == 0


@pytest.mark.parametrize(
    "criteria",
    [
        {"availability_scope": "all"},
        {"status": "unknown"},
        {"match_state": "stale"},
        {"match_state": "missing"},
    ],
)
def test_historical_alert_criteria_rejected(candidate, criteria):
    assert (
        candidate.post(
            P + "/alerts", json={"name": "TEST ONLY invalid", "criteria": criteria}
        ).status_code
        == 422
    )


def test_preferences_default_off_and_copy_ownership(candidate, other, source):
    assert (
        candidate.get(P + "/notifications/preferences").json()["preferences"]["job_alerts"] is False
    )
    saved = candidate.post(
        P + "/saved-searches", json={"name": "TEST ONLY saved", "criteria": {"q": "engineer"}}
    ).json()
    assert candidate.get(P + "/alerts").json()["total"] == 0
    a = alert(candidate, saved_search_id=saved["id"])
    assert a["criteria"]["q"] is None  # explicit criteria is retained
    r = candidate.post(
        P + "/alerts", json={"name": "TEST ONLY copied", "saved_search_id": saved["id"]}
    )
    assert r.status_code == 201 and r.json()["criteria"]["q"] == "engineer"
    assert (
        other.post(
            P + "/alerts", json={"name": "TEST ONLY stolen", "saved_search_id": saved["id"]}
        ).status_code
        == 404
    )
    assert other.delete(P + f"/alerts/{a['id']}").status_code == 404
    ingest(source)
    worker.background_once()
    assert count(Notification) == 0


def test_pause_and_revision_conflict(candidate, source):
    optin(candidate)
    a = alert(candidate)
    ingest(source)
    body = {"name": a["name"], "criteria": {}, "enabled": False, "expected_revision": a["revision"]}
    assert candidate.put(P + f"/alerts/{a['id']}", json=body).status_code == 200
    assert candidate.put(P + f"/alerts/{a['id']}", json=body).status_code == 409
    worker.background_once()
    assert count(Notification) == 0


def test_queued_delivery_rechecks_preferences(candidate, source):
    optin(candidate)
    alert(candidate)
    ingest(source)
    worker.background_once(max_deliveries=0)
    assert count(Notification) == 1
    optin(candidate, job_alerts=False)
    worker.background_once()
    with SessionLocal() as db:
        assert db.scalar(select(NotificationOutbox.status)) == "suppressed"
    assert candidate.get(P + "/notifications").json()["total"] == 0


def test_reminder_due_ownership_completion_and_read(candidate, other, seeded_jobs):
    a = application(candidate, seeded_jobs)
    r, body = reminder(candidate, a["id"], note="TEST ONLY private note")
    assert (
        other.put(P + f"/reminders/{r['id']}", json={**body, "expected_revision": 1}).status_code
        == 404
    )
    worker.background_once()
    worker.background_once()
    ns = candidate.get(P + "/notifications").json()["items"]
    assert len(ns) == 1 and ns[0]["application_id"] == a["id"]
    assert "private note" not in ns[0]["message"]
    assert (
        candidate.post(
            P + f"/reminders/{r['id']}/action", json={"action": "complete", "expected_revision": 1}
        ).json()["status"]
        == "completed"
    )
    worker.background_once()
    assert count(Notification) == 1


@pytest.mark.parametrize("action", ["cancel", "complete"])
def test_cancelled_completed_not_delivered(candidate, seeded_jobs, action):
    a = application(candidate, seeded_jobs)
    r, _ = reminder(candidate, a["id"])
    assert (
        candidate.post(
            P + f"/reminders/{r['id']}/action", json={"action": action, "expected_revision": 1}
        ).status_code
        == 200
    )
    worker.background_once()
    assert count(Notification) == 0


def test_edit_cancels_old_due_task(candidate, seeded_jobs):
    a = application(candidate, seeded_jobs)
    r, b = reminder(candidate, a["id"])
    b["local_time"] = (utcnow() + timedelta(days=2)).replace(tzinfo=None).isoformat()
    response = candidate.put(P + f"/reminders/{r['id']}", json={**b, "expected_revision": 1})
    assert response.status_code == 200 and response.json()["revision"] == 2
    assert (
        candidate.put(P + f"/reminders/{r['id']}", json={**b, "expected_revision": 1}).status_code
        == 409
    )
    worker.background_once()
    assert count(Notification) == 0
    with SessionLocal() as db:
        assert set(db.scalars(select(AutomationTask.status))) == {"cancelled", "queued"}


def test_withdrawn_app_cancels_reminders(candidate, seeded_jobs):
    a = application(candidate, seeded_jobs)
    reminder(candidate, a["id"])
    response = candidate.patch(
        P + f"/applications/{a['id']}",
        json={"status": "withdrawn", "expected_version": a["version"]},
    )
    assert response.status_code == 200, response.text
    worker.background_once()
    assert count(Notification) == 0
    assert candidate.get(P + "/reminders").json()["items"][0]["status"] == "cancelled"


def test_reminder_preference_pause_retains_due_work(candidate, seeded_jobs):
    a = application(candidate, seeded_jobs)
    reminder(candidate, a["id"])
    optin(candidate, reminders=False)
    worker.background_once()
    assert count(Notification) == 0
    with SessionLocal() as db:
        t = db.scalar(select(AutomationTask))
        assert t.status == "queued" and t.due_at > utcnow()


@pytest.mark.parametrize(
    "wall,zone,fold,expected",
    [
        ("2026-10-29T15:00:00", "Asia/Kolkata", None, "2026-10-29T09:30:00+00:00"),
        ("2026-11-01T01:30:00", "America/New_York", 0, "2026-11-01T05:30:00+00:00"),
        ("2026-11-01T01:30:00", "America/New_York", 1, "2026-11-01T06:30:00+00:00"),
    ],
)
def test_timezone_conversion(wall, zone, fold, expected):
    assert local_instant(datetime.fromisoformat(wall), zone, fold).isoformat() == expected


@pytest.mark.parametrize(
    "wall,zone",
    [
        ("2026-03-08T02:30:00", "America/New_York"),
        ("2026-11-01T01:30:00", "America/New_York"),
        ("2026-10-29T15:00:00", "No/Such_Zone"),
    ],
)
def test_dst_gap_fold_and_invalid_zone_rejected(wall, zone):
    with pytest.raises(HTTPException):
        local_instant(datetime.fromisoformat(wall), zone)


def test_concurrent_task_claim_and_fence(candidate, source):
    optin(candidate)
    alert(candidate)
    ingest(source)
    with ThreadPoolExecutor(2) as pool:
        claims = list(pool.map(lambda _: worker.claim_task(), range(2)))
    assert sum(c is not None for c in claims) == 1
    claim = next(c for c in claims if c)
    assert worker.process_task((claim[0], claim[1] - timedelta(seconds=1))) is False
    assert worker.process_task(claim) is True
    assert worker.process_task(claim) is False
    assert count(Notification) == 1


def test_interrupted_task_recovery_bounded(source):
    ingest(source)
    for i in range(3):
        with SessionLocal.begin() as db:
            t = db.scalar(select(AutomationTask))
            t.status = "running"
            t.lease_until = utcnow() - timedelta(seconds=1)
        worker.recover_leases()
    with SessionLocal() as db:
        t = db.scalar(select(AutomationTask))
        assert t.status == "failed" and t.retries == 3


def test_email_optional_unconfigured_and_operator_authorization(candidate):
    assert candidate.put(P + "/notifications/preferences", json={"email": True}).status_code == 422
    for path in ["/automation/status", "/automation/tasks", "/automation/deliveries"]:
        assert candidate.get(P + path).status_code == 403


def prepare_email(c, source, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "test.invalid")
    monkeypatch.setattr(settings, "smtp_sender", "test@example.com")
    optin(c, email=True)
    alert(c, email=True)
    ingest(source)
    worker.background_once(max_deliveries=0)
    with SessionLocal.begin() as db:
        for item in db.scalars(
            select(NotificationOutbox).where(NotificationOutbox.channel == "in_app")
        ):
            item.status = "suppressed"


@pytest.mark.parametrize(
    "outcome,expected",
    [
        ("retry", "retry_scheduled"),
        ("failed", "failed"),
        ("uncertain", "uncertain"),
        ("success", "delivered"),
    ],
)
def test_email_adapter_outcomes_persist(candidate, source, monkeypatch, outcome, expected):
    prepare_email(candidate, source, monkeypatch)

    def sender(n, recipient):
        assert n.category == "new_listing" and recipient == "candidate@example.com"
        if outcome != "success":
            raise EmailResult("TEST_ONLY", outcome)

    claim = worker.claim_delivery()
    assert worker.deliver(claim, sender)
    assert worker.deliver(claim, sender) is False
    with SessionLocal() as db:
        box = db.scalar(select(NotificationOutbox).where(NotificationOutbox.channel == "email"))
        assert box.status == expected
        assert db.scalar(select(DeliveryAttempt.status)) == expected


def test_interrupted_email_uncertain_no_retry_and_reconcile(candidate, source, monkeypatch):
    prepare_email(candidate, source, monkeypatch)
    claim = worker.claim_delivery()
    with SessionLocal.begin() as db:
        box = db.get(NotificationOutbox, claim[0])
        box.lease_until = utcnow() - timedelta(seconds=1)
    worker.recover_leases()
    assert worker.claim_delivery() is None
    assert (
        candidate.post(
            P + f"/automation/deliveries/{claim[0]}/reconcile",
            json={"decision": "failed", "evidence": "TEST ONLY provider confirms no delivery"},
        ).status_code
        == 403
    )
    with SessionLocal.begin() as db:
        db.scalar(select(User)).is_operator = True
    r = candidate.post(
        P + f"/automation/deliveries/{claim[0]}/reconcile",
        json={"decision": "failed", "evidence": "TEST ONLY provider confirms no delivery"},
    )
    assert r.status_code == 200 and r.json()["status"] == "failed"
    assert worker.claim_delivery() is None


def test_schedule_validation_and_pause(candidate, source):
    with SessionLocal.begin() as db:
        db.scalar(select(User)).is_operator = True
    path = P + f"/automation/sources/{source}/schedule"
    assert candidate.put(path, json={"enabled": True, "interval_hours": 1}).status_code == 422
    assert (
        candidate.put(
            path, json={"enabled": True, "interval_hours": 24, "page_limit": 1}
        ).status_code
        == 200
    )
    with SessionLocal() as db:
        s = db.get(JobSource, source)
        assert s.schedule_hours == 24 and s.next_sync_at > utcnow()
    assert candidate.put(path, json={"enabled": False}).status_code == 200
    with SessionLocal() as db:
        assert db.get(JobSource, source).schedule_hours is None


def test_source_retry_lineage_cooldown_and_bound(source):
    from app.db.models import IngestionRun
    from app.modules.automation.sources import coordinate_sources, retry_time

    run = execute(source, AdapterFixture(error_at=1))
    with SessionLocal.begin() as db:
        old = db.get(IngestionRun, run.id)
        old.retry_at = utcnow() - timedelta(seconds=1)
    coordinate_sources()
    coordinate_sources()
    with SessionLocal() as db:
        runs = db.scalars(select(IngestionRun).order_by(IngestionRun.started_at)).all()
        assert len(runs) == 2
        follow = next(r for r in runs if r.id != run.id)
        assert (
            follow.attempt_number == 2
            and follow.root_run_id == run.id
            and follow.status == "queued"
        )
        assert db.get(IngestionRun, run.id).retry_spawned is True
        follow.attempt_number = 3
        assert retry_time(follow, "provider_unavailable") is None
        assert retry_time(follow, "invalid_response") is None


def test_event_task_transaction_rollback(source):
    from app.ingestion.persistence import persist_observation
    from app.modules.sources.contracts import Verification
    from app.modules.sources.normalization import normalize_himalayas

    with SessionLocal() as db:
        persist_observation(
            db,
            normalize_himalayas(raw_job(), source),
            Verification("active", "single_job_api_open", utcnow()),
        )
        db.rollback()
    assert count(Job) == count(JobEvent) == count(AutomationTask) == 0


@pytest.mark.parametrize(
    "phase,outcome",
    [
        ("connect", "retry"),
        ("tls", "failed"),
        ("data", "retry"),
        ("lost_response", "uncertain"),
        ("success", "accepted"),
    ],
)
def test_smtp_protocol_classification_and_private_content(monkeypatch, phase, outcome):
    import smtplib
    from types import SimpleNamespace

    from app.modules.automation import email

    monkeypatch.setattr(settings, "smtp_host", "test.invalid")
    monkeypatch.setattr(settings, "smtp_sender", "test@example.com")

    class SMTP:
        def __init__(self, *args, **kw):
            if phase == "connect":
                raise OSError("TEST ONLY connection failure")

        def ehlo(self):
            pass

        def starttls(self, **kw):
            if phase == "tls":
                raise smtplib.SMTPNotSupportedError("TEST ONLY")

        def send_message(self, message):
            text = message.as_string()
            assert "SECRET PROFILE" not in text and "TEST ONLY job content" not in text
            assert "/notifications" in text
            if phase == "data":
                raise smtplib.SMTPDataError(450, b"TEST ONLY temporary")
            if phase == "lost_response":
                raise OSError("TEST ONLY response lost")

        def close(self):
            pass

    monkeypatch.setattr(email.smtplib, "SMTP", SMTP)
    n = SimpleNamespace(id="test-only", message="TEST ONLY job content", title="SECRET PROFILE")
    if outcome == "accepted":
        assert email.send(n, "test@example.com") == "accepted"
    else:
        with pytest.raises(EmailResult) as exc:
            email.send(n, "test@example.com")
        assert exc.value.outcome == outcome


def test_verification_reuse_then_due_reverification_changes_persisted_eligibility(source):
    from app.modules.automation.notifications import eligible

    ingest(source)
    with SessionLocal() as db:
        verified = db.scalar(select(Job)).last_verified_at
        assert eligible(db.scalar(select(Job)))
    cached = AdapterFixture([SourcePage([raw_job()], None)], verification="closed")
    execute(source, cached)
    assert cached.verifications == []
    with SessionLocal() as db:
        job = db.scalar(select(Job))
        assert job.status == "active" and job.last_verified_at == verified and eligible(job)
    with SessionLocal.begin() as db:
        db.scalar(select(Job)).last_verified_at = utcnow() - timedelta(minutes=11)
    due = AdapterFixture([SourcePage([raw_job()], None)], verification="closed")
    execute(source, due)
    assert len(due.verifications) == 1
    with SessionLocal() as db:
        job = db.scalar(select(Job))
        assert job.status == "closed" and job.last_verified_at > verified and not eligible(job)
        assert db.scalars(select(JobEvent.kind).order_by(JobEvent.created_at)).all() == [
            "new_listing",
            "availability_change",
        ]


@pytest.mark.parametrize("state", ["current", "stale", "insufficient"])
def test_score_subscription_reuses_current_assessment_only(candidate, source, state):
    from app.db.models import MatchResult

    candidate.post(P + "/profile/skills", json={"name": "Python"})
    candidate.patch(P + "/profile", json={"headline": "Software engineer"})
    optin(candidate)
    alert(candidate, criteria={"minimum_score": 0})
    ingest(
        source, title="TEST ONLY Software engineer", description="<p>Required skills: Python</p>"
    )
    result = candidate.post(P + "/matches/refresh", json={})
    assert result.status_code == 200, result.text
    if state == "stale":
        candidate.post(P + "/profile/skills", json={"name": "Java"})
    if state == "insufficient":
        with SessionLocal.begin() as db:
            m = db.scalar(select(MatchResult))
            m.score = None
            m.assessment_status = "insufficient_information"
    before = count(MatchResult)
    worker.background_once()
    assert count(Notification) == (1 if state == "current" else 0)
    assert count(MatchResult) == before


@pytest.mark.parametrize(
    "patch",
    [
        {"description": "<p>Required: Python. Preferred: SQL.</p>"},
        {"minSalary": 70000},
        {"employmentType": "Contractor"},
        {"locationRestrictions": ["Canada"]},
    ],
)
def test_material_source_conditions_create_one_update_event(source, patch):
    ingest(source)
    ingest(source, **patch)
    ingest(source, **patch)
    with SessionLocal() as db:
        assert db.scalars(select(JobEvent.kind).order_by(JobEvent.created_at)).all() == [
            "new_listing",
            "material_update",
        ]


def test_concurrent_canonical_persistence_deduplicates_event(source):
    from app.ingestion.persistence import persist_observation
    from app.modules.sources.contracts import Verification
    from app.modules.sources.normalization import normalize_himalayas

    def persist(_):
        with SessionLocal.begin() as db:
            persist_observation(
                db,
                normalize_himalayas(raw_job(), source),
                Verification("active", "single_job_api_open", utcnow()),
            )

    with ThreadPoolExecutor(2) as pool:
        list(pool.map(persist, range(2)))
    assert count(Job) == count(JobEvent) == count(AutomationTask) == 1


def test_task_rollback_transient_retry_and_inapp_delivery_budget(
    candidate, seeded_jobs, monkeypatch
):
    from sqlalchemy.exc import OperationalError

    a = application(candidate, seeded_jobs)
    reminder(candidate, a["id"])
    original = worker.process_reminder

    def fail(db, task):
        original(db, task)
        raise OperationalError("TEST ONLY", {}, Exception("TEST ONLY"))

    monkeypatch.setattr(worker, "process_reminder", fail)
    claim = worker.claim_task()
    assert worker.process_task(claim) is False
    assert count(Notification) == 0
    with SessionLocal.begin() as db:
        t = db.scalar(select(AutomationTask))
        assert t.status == "retry_scheduled"
        t.due_at = utcnow()
    monkeypatch.setattr(worker, "process_reminder", original)
    worker.background_once(max_deliveries=0)
    assert count(Notification) == 1
    for attempt in range(3):
        claim = worker.claim_delivery()
        assert claim
        with SessionLocal.begin() as db:
            db.get(NotificationOutbox, claim[0]).lease_until = utcnow() - timedelta(seconds=1)
        worker.recover_leases()
    assert worker.claim_delivery() is None
    with SessionLocal() as db:
        b = db.scalar(select(NotificationOutbox))
        assert b.status == "failed" and b.attempts == 3


def test_deleted_application_cascades_reminder_and_cancels_task(candidate, seeded_jobs):
    from app.db.models import Application, ApplicationReminder

    a = application(candidate, seeded_jobs)
    reminder(candidate, a["id"])
    with SessionLocal.begin() as db:
        db.delete(db.get(Application, a["id"]))
    worker.background_once()
    assert count(ApplicationReminder) == count(Notification) == 0
    with SessionLocal() as db:
        assert db.scalar(select(AutomationTask.status)) == "cancelled"


def test_request_spacing_persists_between_source_runs(source, monkeypatch):
    from app.ingestion.control import queue_run, source_lock
    from app.ingestion.service import provider_progress

    with SessionLocal.begin() as db:
        run = queue_run(db, source)
        key = run.id
    fixed = utcnow()
    monkeypatch.setattr("app.ingestion.service.utcnow", lambda: fixed)
    sleeps = []
    with source_lock("provider:himalayas") as acquired:
        assert acquired
        provider_progress(key, sleep=sleeps.append)
        provider_progress(key, sleep=sleeps.append)
    assert sleeps == [1.1]


def test_source_recovery_does_not_steal_live_lock(source):
    from app.db.models import IngestionRun
    from app.ingestion.control import queue_run, source_lock
    from app.modules.automation.sources import coordinate_sources

    with SessionLocal.begin() as db:
        run = queue_run(db, source)
        run.status = "running"
        run.heartbeat_at = utcnow() - timedelta(minutes=11)
        key = run.id
    with source_lock(source) as acquired:
        assert acquired
        coordinate_sources()
        with SessionLocal() as db:
            assert db.get(IngestionRun, key).status == "running"
    coordinate_sources()
    with SessionLocal() as db:
        run = db.get(IngestionRun, key)
        assert run.status == "interrupted" and run.retry_at > utcnow()
