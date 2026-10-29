from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select

from app.core.security import utcnow
from app.db.models import IngestionRun, JobSource
from app.db.session import SessionLocal
from app.ingestion.control import queue_run, source_lock
from app.modules.automation.notifications import operator_failure

TRANSIENT = {
    "rate_limited",
    "provider_unavailable",
    "network_timeout_or_failure",
    "verification_cooldown",
    "worker_interrupted",
}


def retry_time(run, error_code, retry_at=None):
    if error_code not in TRANSIENT or run.attempt_number >= 3:
        return None
    backoff = utcnow() + timedelta(seconds=60 * 2 ** (run.attempt_number - 1))
    return max(backoff, retry_at) if retry_at else backoff


def coordinate_sources():
    now = utcnow()
    with SessionLocal() as db:
        expired = list(
            db.execute(
                select(IngestionRun.id, IngestionRun.source_id)
                .where(
                    IngestionRun.status == "running",
                    IngestionRun.heartbeat_at < now - timedelta(minutes=10),
                )
                .limit(20)
            )
        )
    for run_id, source_id in expired:
        with source_lock(source_id) as acquired:
            if not acquired:
                continue
            with SessionLocal.begin() as db:
                run = db.get(IngestionRun, run_id)
                if run.status != "running" or run.heartbeat_at >= now - timedelta(minutes=10):
                    continue
                run.status = "interrupted"
                run.error_code = "worker_interrupted"
                run.finished_at = now
                run.retry_at = retry_time(run, run.error_code)
                source = db.get(JobSource, source_id)
                source.operational_status = "interrupted"
                source.error_code = run.error_code
                operator_failure(
                    db,
                    "source:" + run.id,
                    "A synchronization worker was interrupted. Committed page checkpoints are retained.",
                    run.id,
                )
    with SessionLocal.begin() as db:
        candidates = db.scalars(
            select(IngestionRun)
            .where(
                IngestionRun.retry_at <= now,
                IngestionRun.retry_spawned.is_(False),
                IngestionRun.status.in_(["failed", "partial", "interrupted"]),
            )
            .with_for_update(skip_locked=True, of=IngestionRun)
            .limit(20)
        ).all()
        for previous in candidates:
            source = db.scalar(
                select(JobSource)
                .where(JobSource.id == previous.source_id)
                .with_for_update(skip_locked=True)
            )
            if (
                not source
                or not source.enabled
                or (source.not_before_at and source.not_before_at > now)
            ):
                continue
            if db.scalar(
                select(IngestionRun.id).where(
                    IngestionRun.source_id == source.id,
                    IngestionRun.status.in_(["queued", "running"]),
                )
            ):
                continue
            run = queue_run(db, source.id, "retry")
            run.start_cursor = run.next_cursor = previous.next_cursor
            run.attempt_number = previous.attempt_number + 1
            run.root_run_id = previous.root_run_id or previous.id
            previous.retry_spawned = True


def configure_schedule(db, source_id, data):
    source = db.scalar(select(JobSource).where(JobSource.id == source_id).with_for_update())
    if not source:
        raise HTTPException(404, "Source not found")
    if source.adapter_key != "himalayas" or not source.enabled:
        raise HTTPException(
            422,
            "Enable the installed Himalayas source through the existing trusted configuration first",
        )
    source.schedule_hours = data.interval_hours if data.enabled else None
    source.next_sync_at = utcnow() + timedelta(hours=data.interval_hours) if data.enabled else None
    source.page_limit = data.page_limit
    db.flush()
    return {
        "source_id": source.id,
        "schedule_enabled": bool(source.schedule_hours),
        "interval_hours": source.schedule_hours,
        "next_sync_at": source.next_sync_at,
        "page_limit": source.page_limit,
    }
