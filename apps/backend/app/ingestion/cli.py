"""Trusted local operator controls. No credentials are accepted as CLI arguments."""

import argparse
import json
import os
import time
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from app.core.security import utcnow
from app.db.models import AuditEvent, IngestionRun, JobSource, User
from app.db.session import SessionLocal
from app.ingestion.control import queue_run, source_lock
from app.ingestion.service import process_run


def configure_source(page_limit=2, schedule_hours=None):
    with SessionLocal.begin() as db:
        source = db.scalar(select(JobSource).where(JobSource.adapter_key == "himalayas"))
        if not source:
            source = JobSource(
                name="Himalayas",
                source_type="api",
                adapter_key="himalayas",
                enabled=True,
                operational_status="never_synced",
            )
            db.add(source)
        source.page_limit = page_limit
        source.schedule_hours = schedule_hours
        source.next_sync_at = utcnow() + timedelta(hours=schedule_hours) if schedule_hours else None
        db.flush()
        return source.id


def work_once(schedule=False):
    if schedule:
        with SessionLocal.begin() as db:
            # Row locks coordinate scheduler copies; the partial unique index also
            # prevents more than one queued/running run for each source.
            due = db.scalars(
                select(JobSource)
                .where(
                    JobSource.enabled.is_(True),
                    JobSource.schedule_hours.is_not(None),
                    JobSource.next_sync_at <= utcnow(),
                )
                .with_for_update(skip_locked=True)
            ).all()
            for source in due:
                active = db.scalar(
                    select(IngestionRun.id).where(
                        IngestionRun.source_id == source.id,
                        IngestionRun.status.in_(["queued", "running"]),
                    )
                )
                if not active and (
                    source.not_before_at is None or source.not_before_at <= utcnow()
                ):
                    queue_run(db, source.id, "scheduled")
    with SessionLocal() as db:
        queued = db.scalars(
            select(IngestionRun.id)
            .where(IngestionRun.status == "queued")
            .order_by(IngestionRun.created_at)
            .limit(10)
        ).all()
    for run_id in queued:
        if process_run(run_id):
            return True
    return False


def recover(run_id):
    with SessionLocal() as db:
        run = db.get(IngestionRun, run_id)
        if not run:
            raise ValueError("Unknown run")
        source_id = run.source_id
    with source_lock(source_id) as acquired:
        if not acquired:
            raise ValueError("A worker still owns this source; recovery refused")
        with SessionLocal.begin() as db:
            run = db.get(IngestionRun, run_id)
            if run.status not in {"queued", "running"}:
                raise ValueError("Run is already finished")
            run.status = "interrupted"
            run.error_code = "operator_recovered_interruption"
            run.finished_at = utcnow()
            source = db.get(JobSource, source_id)
            source.operational_status = "interrupted"
            source.error_code = run.error_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    configure = commands.add_parser("configure")
    configure.add_argument("--page-limit", type=int, choices=range(1, 26), default=2)
    configure.add_argument("--schedule-hours", type=int)
    sync = commands.add_parser("sync")
    sync.add_argument("--source-id", required=True)
    sync.add_argument("--resume-run-id")
    sync.add_argument("--queue-only", action="store_true")
    worker = commands.add_parser("worker")
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--schedule", action="store_true")
    worker.add_argument("--stop-file", type=Path)
    worker.add_argument("--runtime-state", type=Path)
    recovery = commands.add_parser("recover")
    recovery.add_argument("--run-id", required=True)
    promote = commands.add_parser("promote")
    promote.add_argument("--email", required=True)
    promote.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    if args.command == "configure":
        if args.schedule_hours is not None and args.schedule_hours < 24:
            parser.error("Himalayas scheduling must be at least 24 hours")
        print(json.dumps({"source_id": configure_source(args.page_limit, args.schedule_hours)}))
    elif args.command == "sync":
        with SessionLocal.begin() as db:
            run = queue_run(db, args.source_id, "cli", resume_run_id=args.resume_run_id)
            run_id = run.id
        if not args.queue_only:
            process_run(run_id)
        with SessionLocal() as db:
            run = db.get(IngestionRun, run_id)
            print(
                json.dumps(
                    {
                        key: getattr(run, key)
                        for key in [
                            "id",
                            "status",
                            "pages",
                            "fetched",
                            "accepted",
                            "inserted",
                            "updated",
                            "unchanged",
                            "duplicates",
                            "rejected",
                            "skipped",
                            "retried",
                            "errors",
                            "error_code",
                        ]
                    }
                )
            )
    elif args.command == "worker":
        from app.operations.worker_health import record

        if args.runtime_state:
            os.environ["JSI_WORKER_STATE_PATH"] = str(args.runtime_state)
        record(status="starting", current_task=None)
        while not (args.stop_file and args.stop_file.exists()):
            from app.modules.automation.sources import coordinate_sources
            from app.modules.automation.worker import background_once

            record(status="running", current_task="source_coordination")
            coordinate_sources()
            record(status="running", current_task="source_sync")
            work_once(args.schedule)
            record(status="running", current_task="automation_pass")
            background_once()
            record(status="idle", current_task=None)
            if args.once:
                break
            time.sleep(5)
        record(status="stopped", current_task=None)
    elif args.command == "recover":
        recover(args.run_id)
        print("Run marked interrupted; committed page checkpoints and jobs were preserved.")
    elif args.command == "promote":
        with SessionLocal.begin() as db:
            user = db.scalar(select(User).where(User.email == args.email.lower()))
            if not user:
                parser.error("Register this account first; no account was created or bypassed")
            user.is_operator = not args.revoke
            db.add(
                AuditEvent(
                    user_id=user.id,
                    action="operator.revoked" if args.revoke else "operator.granted",
                    resource_id=user.id,
                )
            )
        print("Operator access updated for the selected existing account.")


if __name__ == "__main__":
    main()
