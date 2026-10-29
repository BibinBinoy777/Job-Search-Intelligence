import hashlib
from contextlib import contextmanager
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, text

from app.core.security import utcnow
from app.db.models import AuditEvent, IngestionRecord, IngestionRun, JobSource
from app.db.repositories import paginate
from app.db.session import engine


def lock_key(source_id):
    return int.from_bytes(hashlib.sha256(source_id.encode()).digest()[:8], "big", signed=True)


@contextmanager
def source_lock(source_id):
    # Session-level advisory locks survive page commits and are released on crash.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        acquired = conn.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key(source_id)}
        )
        try:
            yield acquired
        finally:
            if acquired:
                conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key(source_id)})


def queue_run(db, source_id, trigger="manual", user_id=None, resume_run_id=None):
    source = db.get(JobSource, source_id)
    if source is None:
        raise HTTPException(404, "Source not found")
    if not source.enabled or source.adapter_key != "himalayas":
        raise HTTPException(422, "Source is disabled or has no installed adapter")
    if source.not_before_at and source.not_before_at > utcnow():
        raise HTTPException(429, "Source cooldown is active. Retry after the recorded time")
    if db.scalar(
        select(IngestionRun.id).where(
            IngestionRun.source_id == source_id, IngestionRun.status.in_(["queued", "running"])
        )
    ):
        raise HTTPException(409, "This source already has a queued or running synchronization")
    cursor = None
    if resume_run_id:
        previous = db.get(IngestionRun, resume_run_id)
        if (
            not previous
            or previous.source_id != source_id
            or previous.status in {"queued", "running"}
        ):
            raise HTTPException(422, "Resume requires a finished run for the same source")
        cursor = previous.next_cursor
        if not cursor:
            raise HTTPException(422, "This run has no resumable continuation")
    run = IngestionRun(
        source_id=source_id,
        trigger=trigger,
        requested_by=user_id,
        max_pages=source.page_limit,
        start_cursor=cursor,
        next_cursor=cursor,
    )
    db.add(run)
    if source.schedule_hours:
        source.next_sync_at = utcnow() + timedelta(hours=source.schedule_hours)
    db.flush()
    db.add(AuditEvent(user_id=user_id, action="ingestion.queued", resource_id=run.id))
    return run


def list_runs(db, page, page_size, source_id=None):
    stmt = select(IngestionRun)
    if source_id:
        stmt = stmt.where(IngestionRun.source_id == source_id)
    return paginate(
        db, stmt.order_by(IngestionRun.created_at.desc(), IngestionRun.id), page, page_size
    )


def get_run(db, run_id):
    item = db.get(IngestionRun, run_id)
    if item is None:
        raise HTTPException(404, "Ingestion run not found")
    return item


def run_records(db, run_id, page, page_size):
    get_run(db, run_id)
    return paginate(
        db,
        select(IngestionRecord)
        .where(IngestionRecord.run_id == run_id)
        .order_by(IngestionRecord.page_number, IngestionRecord.record_number),
        page,
        page_size,
    )
