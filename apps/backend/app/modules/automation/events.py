from app.core.security import utcnow
from app.db.models import AutomationTask, JobEvent
from app.modules.matching.representations import fingerprint, job_snapshot


def content_version(job):
    # Observation/cache/verification dates never create a material-update alert.
    snapshot = job_snapshot(job)
    for key in ["location_restrictions", "timezone_restrictions", "source_categories"]:
        snapshot[key] = sorted(snapshot[key] or [], key=str)
    return fingerprint({**snapshot, "employer": job.employer, "source_url": job.source_url})


def capture(db, job, old_content, old_status, inserted, run_id=None):
    current = content_version(job)
    kinds = ["new_listing"] if inserted else (["material_update"] if old_content != current else [])
    if not inserted and old_status != job.status:
        kinds.append("availability_change")
    if not kinds:
        return
    job.event_sequence += 1
    for kind in kinds:
        event = JobEvent(
            job_id=job.id,
            run_id=run_id,
            sequence=job.event_sequence,
            kind=kind,
            content_fingerprint=current,
            resulting_status=job.status,
        )
        db.add(event)
        db.flush()
        if kind != "availability_change":
            db.add(
                AutomationTask(
                    kind="job_alert",
                    event_id=event.id,
                    dedupe_key="event:" + event.id,
                    due_at=utcnow(),
                )
            )
    db.flush()
