from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.core.security import utcnow
from app.db.models import (
    ApplicationReminder,
    AutomationHeartbeat,
    AutomationTask,
    DeliveryAttempt,
    Notification,
    NotificationOutbox,
    User,
)
from app.db.session import SessionLocal
from app.modules.automation import email
from app.modules.automation.notifications import (
    evaluate_event,
    operator_failure,
    permitted_delivery,
    process_reminder,
)


def recover_leases():
    now = utcnow()
    with SessionLocal.begin() as db:
        expired = db.scalars(
            select(AutomationTask)
            .where(AutomationTask.status == "running", AutomationTask.lease_until < now)
            .with_for_update(skip_locked=True)
            .limit(50)
        ).all()
        for task in expired:
            task.retries += 1
            task.error_code = "worker_interrupted"
            task.lease_until = None
            task.status = "retry_scheduled" if task.retries < 3 else "failed"
            task.due_at = now + timedelta(seconds=30 * 2 ** min(task.retries, 3))
            if task.status == "failed":
                task.finished_at = now
                operator_failure(
                    db,
                    "task:" + task.id,
                    "A background task exhausted its recovery budget. Inspect automation history.",
                )
        for outbox in db.scalars(
            select(NotificationOutbox)
            .where(NotificationOutbox.status == "sending", NotificationOutbox.lease_until < now)
            .with_for_update(skip_locked=True)
            .limit(50)
        ):
            outbox.status = (
                "uncertain"
                if outbox.channel == "email"
                else ("failed" if outbox.attempts >= 3 else "retry_scheduled")
            )
            outbox.error_code = (
                "delivery_interrupted_unknown"
                if outbox.channel == "email"
                else "delivery_interrupted"
            )
            if outbox.status in {"failed", "uncertain"}:
                operator_failure(
                    db,
                    "delivery:" + outbox.id,
                    "A notification delivery needs operator review. Inspect delivery history.",
                )
            outbox.due_at = now
            outbox.lease_until = None
            attempt = db.scalar(
                select(DeliveryAttempt).where(
                    DeliveryAttempt.outbox_id == outbox.id,
                    DeliveryAttempt.number == outbox.attempts,
                )
            )
            if attempt:
                attempt.status = outbox.status
                attempt.error_code = outbox.error_code
                attempt.finished_at = now
        # Stale future reminder tasks are cancelled without acquiring reminder
        # locks; reminder APIs never lock task rows in the opposite order.
        for task in db.scalars(
            select(AutomationTask)
            .where(
                AutomationTask.kind == "reminder",
                AutomationTask.status.in_(["queued", "retry_scheduled"]),
            )
            .with_for_update(skip_locked=True)
            .limit(100)
        ):
            reminder = db.get(ApplicationReminder, task.reminder_id) if task.reminder_id else None
            if (
                not reminder
                or reminder.revision != task.reminder_revision
                or reminder.status in {"completed", "cancelled"}
            ):
                task.status = "cancelled"
                task.finished_at = now


def claim_task():
    with SessionLocal.begin() as db:
        task = db.scalar(
            select(AutomationTask)
            .where(
                AutomationTask.status.in_(["queued", "retry_scheduled"]),
                AutomationTask.due_at <= utcnow(),
            )
            .order_by(AutomationTask.due_at, AutomationTask.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not task:
            return None
        task.status = "running"
        task.attempts += 1
        task.started_at = utcnow()
        task.lease_until = utcnow() + timedelta(minutes=2)
        return task.id, task.lease_until


def process_task(claim):
    task_id, lease = claim
    try:
        with SessionLocal.begin() as db:
            task = db.scalar(
                select(AutomationTask).where(AutomationTask.id == task_id).with_for_update()
            )
            if not task or task.status != "running" or task.lease_until != lease:
                return False
            if task.kind == "job_alert":
                done, outcome = evaluate_event(db, task)
            elif task.kind == "reminder":
                done, outcome = process_reminder(db, task)
            else:
                raise ValueError("unsupported_task")
            task.outcome = outcome
            task.error_code = None
            task.lease_until = None
            task.status = (
                "cancelled" if outcome.get("cancelled") else "completed" if done else "queued"
            )
            if done:
                task.finished_at = utcnow()
            elif not outcome.get("preferences_paused") and not outcome.get("not_due"):
                task.due_at = utcnow()
        return True
    except Exception as exc:
        from sqlalchemy.exc import SQLAlchemyError

        code = "database_unavailable" if isinstance(exc, SQLAlchemyError) else "task_failed"
        with SessionLocal.begin() as db:
            task = db.scalar(
                select(AutomationTask).where(AutomationTask.id == task_id).with_for_update()
            )
            if not task or task.status != "running" or task.lease_until != lease:
                return False
            task.retries += 1
            task.error_code = code
            task.lease_until = None
            task.status = (
                "retry_scheduled"
                if code == "database_unavailable" and task.retries < 3
                else "failed"
            )
            task.due_at = utcnow() + timedelta(seconds=30 * 2**task.retries)
            if task.status == "failed":
                task.finished_at = utcnow()
                operator_failure(
                    db,
                    "task:" + task.id,
                    "A background task failed. Inspect its safe error category in automation history.",
                )
        return False


def claim_delivery():
    with SessionLocal.begin() as db:
        item = db.scalar(
            select(NotificationOutbox)
            .where(
                NotificationOutbox.status.in_(["queued", "retry_scheduled"]),
                NotificationOutbox.due_at <= utcnow(),
            )
            .order_by(NotificationOutbox.due_at, NotificationOutbox.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not item:
            return None
        item.status = "sending"
        item.attempts += 1
        item.lease_until = utcnow() + timedelta(minutes=5)
        db.add(DeliveryAttempt(outbox_id=item.id, number=item.attempts, status="started"))
        return item.id, item.lease_until


def deliver(claim, sender=None):
    outbox_id, lease = claim
    sender = sender or email.send
    with SessionLocal.begin() as db:
        item = db.scalar(
            select(NotificationOutbox).where(NotificationOutbox.id == outbox_id).with_for_update()
        )
        if not item or item.status != "sending" or item.lease_until != lease:
            return False
        notification = db.scalar(
            select(Notification).where(Notification.id == item.notification_id).with_for_update()
        )
        attempt = db.scalar(
            select(DeliveryAttempt).where(
                DeliveryAttempt.outbox_id == item.id, DeliveryAttempt.number == item.attempts
            )
        )
        if not notification or not permitted_delivery(db, notification, item.channel):
            item.status = "suppressed"
            item.lease_until = None
            attempt.status = "suppressed"
            attempt.finished_at = utcnow()
            if notification and item.channel == "in_app":
                notification.in_app_status = "suppressed"
            return True
        if item.channel == "in_app":
            item.status = "delivered"
            item.delivered_at = utcnow()
            item.lease_until = None
            notification.in_app_status = "delivered"
            attempt.status = "delivered"
            attempt.finished_at = utcnow()
            return True
        recipient = db.get(User, notification.user_id).email
        # Sending state and started attempt are already committed by claim.
        detached = notification
    try:
        sender(detached, recipient)
        outcome, code = "delivered", None
    except email.EmailResult as exc:
        outcome, code = exc.outcome, exc.code
    except Exception:
        outcome, code = "uncertain", "email_acceptance_uncertain"
    with SessionLocal.begin() as db:
        item = db.scalar(
            select(NotificationOutbox).where(NotificationOutbox.id == outbox_id).with_for_update()
        )
        if not item or item.status != "sending" or item.lease_until != lease:
            return False
        item.error_code = code
        item.lease_until = None
        item.status = (
            "retry_scheduled"
            if outcome == "retry" and item.attempts < 3
            else "failed"
            if outcome == "retry"
            else outcome
        )
        item.due_at = utcnow() + timedelta(seconds=30 * 2**item.attempts)
        if outcome == "delivered":
            item.delivered_at = utcnow()
        attempt = db.scalar(
            select(DeliveryAttempt).where(
                DeliveryAttempt.outbox_id == item.id, DeliveryAttempt.number == item.attempts
            )
        )
        if item.status in {"failed", "uncertain"}:
            operator_failure(
                db,
                "delivery:" + item.id,
                "A notification delivery needs operator review. Inspect delivery history.",
            )
        attempt.status = item.status
        attempt.error_code = code
        attempt.finished_at = utcnow()
    return True


def background_once(max_tasks=10, max_deliveries=20):
    if not settings.automation_enabled:
        return {"enabled": False}
    recover_leases()
    tasks = deliveries = 0
    for _ in range(max_tasks):
        claim = claim_task()
        if not claim:
            break
        process_task(claim)
        tasks += 1
    for _ in range(max_deliveries):
        claim = claim_delivery()
        if not claim:
            break
        deliver(claim)
        deliveries += 1
    with SessionLocal.begin() as db:
        db.execute(
            insert(AutomationHeartbeat)
            .values(key="shared_worker", last_tick_at=utcnow())
            .on_conflict_do_update(
                index_elements=[AutomationHeartbeat.key], set_={"last_tick_at": utcnow()}
            )
        )
    return {"enabled": True, "tasks_processed": tasks, "deliveries_processed": deliveries}
