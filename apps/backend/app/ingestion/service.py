import hashlib
import time
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from app.core.security import utcnow
from app.db.models import AutomationHeartbeat, IngestionRecord, IngestionRun, Job, JobSource
from app.db.session import SessionLocal
from app.ingestion.control import source_lock
from app.ingestion.persistence import persist_observation
from app.modules.sources.contracts import SourceError, Verification
from app.modules.sources.himalayas import HimalayasAdapter
from app.modules.sources.transport import JsonTransport


def progress(run_id, retry=False):
    with SessionLocal.begin() as db:
        values = {"heartbeat_at": utcnow()}
        if retry:
            values["retried"] = IngestionRun.retried + 1
        db.execute(update(IngestionRun).where(IngestionRun.id == run_id).values(**values))


def provider_progress(run_id, sleep=time.sleep):
    # The provider advisory lock spans this callback and the actual request.
    # Persist spacing across run boundaries and worker processes, too.
    key = "himalayas_last_request"
    with SessionLocal() as db:
        marker = db.get(AutomationHeartbeat, key)
        previous = marker.last_tick_at if marker else None
    if previous:
        sleep(max(0, 1.1 - (utcnow() - previous).total_seconds()))
    with SessionLocal.begin() as db:
        marker = db.get(AutomationHeartbeat, key)
        if marker:
            marker.last_tick_at = utcnow()
        else:
            db.add(AutomationHeartbeat(key=key, last_tick_at=utcnow()))
    progress(run_id)


def cached_verification(source_id, identity):
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.source_id == source_id, Job.external_id == identity))
        if (
            job
            and job.last_verified_at
            and job.last_verified_at >= utcnow() - timedelta(minutes=10)
            and job.status_basis
            in {"single_job_api_open", "single_job_api_closed", "single_job_api_not_found"}
        ):
            return Verification(job.status, job.status_basis, job.last_verified_at)
    return None


def process_run(run_id, adapter=None):
    # One provider budget across worker processes, including accidentally
    # duplicated source configuration rows. Per-source lock remains authoritative.
    with source_lock("provider:himalayas") as acquired:
        return process_source_run(run_id, adapter) if acquired else False


def process_source_run(run_id, adapter=None):
    with SessionLocal() as db:
        queued = db.get(IngestionRun, run_id)
        if not queued:
            raise ValueError("Unknown ingestion run")
        source_id = queued.source_id
    with source_lock(source_id) as acquired:
        if not acquired:
            return False
        with SessionLocal.begin() as db:
            run = db.get(IngestionRun, run_id)
            if run.status != "queued":
                return False
            source = db.get(JobSource, source_id)
            if not source.enabled or source.adapter_key != "himalayas":
                run.status = "failed"
                run.error_code = "source_disabled"
                run.errors += 1
                run.finished_at = utcnow()
                return True
            run.status = "running"
            run.started_at = run.heartbeat_at = utcnow()
            source.last_sync_at = utcnow()
            source.operational_status = "running"
            cursor, max_pages = run.start_cursor, run.max_pages
        adapter = adapter or HimalayasAdapter(
            JsonTransport(
                on_retry=lambda: progress(run_id, True),
                on_request=lambda: provider_progress(run_id),
            )
        )
        seen = set()
        cursors = set()
        try:
            for page_number in range(1, max_pages + 1):
                if cursor in cursors:
                    raise SourceError("repeated_cursor")
                cursors.add(cursor)
                page = adapter.fetch_jobs({"limit": 20}, cursor)
                staged = []
                cooldown = None
                abort_error = None
                for position, raw in enumerate(page.records):
                    identity = None
                    valid_record = False
                    try:
                        identity = adapter.get_source_identity(raw)
                        identity_hash = hashlib.sha256(identity.encode()).hexdigest()
                        if identity in seen:
                            staged.append((position, identity_hash, "duplicate", None, None, None))
                            continue
                        seen.add(identity)
                        normalized = adapter.normalize_job(raw, source_id)
                        valid_record = True
                        verification = cached_verification(
                            source_id, identity
                        ) or adapter.verify_job(identity)
                        staged.append(
                            (position, identity_hash, None, normalized, verification, None)
                        )
                    except (SourceError, ValidationError) as exc:
                        code = (
                            exc.code
                            if isinstance(exc, SourceError)
                            else "canonical_validation_failed"
                        )
                        # Verification failures are skipped; malformed data is rejected.
                        skipped = valid_record
                        identity_hash = (
                            hashlib.sha256(identity.encode()).hexdigest() if identity else None
                        )
                        staged.append(
                            (
                                position,
                                identity_hash,
                                "skipped" if skipped else "rejected",
                                None,
                                None,
                                code,
                            )
                        )
                        if isinstance(exc, SourceError) and exc.retry_at:
                            cooldown = exc.retry_at
                        if code in {
                            "rate_limited",
                            "provider_auth_rejected",
                            "provider_unavailable",
                            "network_timeout_or_failure",
                        }:
                            abort_error = SourceError(
                                code, exc.retry_at if isinstance(exc, SourceError) else None
                            )
                            # Stop further requests after the transport exhausted its budget.
                            for remaining in range(position + 1, len(page.records)):
                                staged.append(
                                    (
                                        remaining,
                                        None,
                                        "skipped",
                                        None,
                                        None,
                                        "page_verification_stopped",
                                    )
                                )
                            break
                with SessionLocal.begin() as db:
                    run = db.get(IngestionRun, run_id)
                    counts = {
                        key: 0
                        for key in [
                            "accepted",
                            "inserted",
                            "updated",
                            "unchanged",
                            "duplicates",
                            "rejected",
                            "skipped",
                            "errors",
                        ]
                    }
                    for position, identity_hash, outcome, normalized, verification, code in staged:
                        job_id = None
                        if outcome is None:
                            try:
                                with db.begin_nested():
                                    item, outcome = persist_observation(
                                        db, normalized, verification, run_id=run_id
                                    )
                                    job_id = item.id
                            except (ValidationError, SQLAlchemyError):
                                outcome, code = "rejected", "record_persistence_rejected"
                        if outcome in {"inserted", "updated", "unchanged"}:
                            counts["accepted"] += 1
                            counts[outcome] += 1
                        else:
                            counts["duplicates" if outcome == "duplicate" else outcome] += 1
                            if outcome != "duplicate":
                                counts["errors"] += 1
                        db.add(
                            IngestionRecord(
                                run_id=run_id,
                                page_number=page_number,
                                record_number=position,
                                identity_hash=identity_hash,
                                job_id=job_id,
                                outcome=outcome,
                                error_code=code,
                            )
                        )
                    for key, value in counts.items():
                        setattr(run, key, getattr(run, key) + value)
                    run.fetched += len(page.records)
                    run.pages += 1
                    run.next_cursor = cursor if abort_error else page.next_cursor
                    run.heartbeat_at = utcnow()
                    if cooldown:
                        db.get(JobSource, source_id).not_before_at = cooldown
                cursor = page.next_cursor
                if abort_error:
                    raise abort_error
                if cooldown:
                    raise SourceError("verification_cooldown", cooldown)
                if cursor is None:
                    break
            finish_run(run_id, None, has_more=cursor is not None)
        except SourceError as exc:
            finish_run(run_id, exc)
        except Exception:
            # No raw exception text, source payload, credential or success simulation.
            finish_run(run_id, SourceError("worker_internal_failure"))
        return True


def finish_run(run_id, error, has_more=False):
    with SessionLocal.begin() as db:
        run = db.get(IngestionRun, run_id)
        source = db.get(JobSource, run.source_id)
        if error:
            run.status = "partial" if run.pages else "failed"
            run.errors += 1
            run.error_code = error.code
            source.error_code = error.code
            if error.retry_at:
                source.not_before_at = error.retry_at
            from app.modules.automation.notifications import operator_failure
            from app.modules.automation.sources import retry_time

            run.retry_at = retry_time(run, error.code, error.retry_at)
            operator_failure(
                db,
                "source:" + run.id,
                "A source synchronization failed or finished partially. Inspect the recorded run and safe error category.",
                run.id,
            )
        elif run.rejected or run.skipped:
            run.status = "partial"
            run.error_code = source.error_code = "record_errors"
        else:
            run.status = "limited" if has_more else "completed"
            source.last_success_at = utcnow()
            source.error_code = None
            if not has_more and run.start_cursor is None:
                source.last_full_sync_at = utcnow()
        run.finished_at = run.heartbeat_at = utcnow()
        source.operational_status = run.status
