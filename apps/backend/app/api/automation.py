from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.api.dependencies import DB, CurrentUser, PageNumber, PageSize
from app.api.schemas import Page
from app.core.config import settings
from app.core.security import utcnow
from app.db.models import (
    ApplicationReminder,
    AutomationHeartbeat,
    AutomationTask,
    DeliveryAttempt,
    IngestionRun,
    Notification,
    NotificationOutbox,
)
from app.db.repositories import paginate
from app.modules.automation import service
from app.modules.automation.schemas import (
    AlertIn,
    AlertOut,
    AlertUpdate,
    NotificationOut,
    NotificationPreferencesIn,
    ReadBatch,
    ReadIn,
    ReconcileIn,
    ReminderAction,
    ReminderIn,
    ReminderOut,
    ReminderUpdate,
    SourceScheduleIn,
    TaskOut,
)
from app.modules.automation.sources import configure_schedule

router = APIRouter(prefix="/api/v1", tags=["Automation and notifications"])


def operator(user):
    if not user.is_operator:
        raise HTTPException(403, "Operator access is required")


@router.get("/notifications/preferences")
def preferences(db: DB, user: CurrentUser):
    return {
        "preferences": service.preferences(db, user.id),
        "email_available": service.email_available(),
        "frequency": "immediate on the next worker pass",
        "quiet_hours_supported": False,
        "worker_required": True,
    }


@router.put("/notifications/preferences")
def put_preferences(data: NotificationPreferencesIn, db: DB, user: CurrentUser):
    return service.put_preferences(db, user.id, data)


def owned_notification(db, user, notification_id):
    item = db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user.id
        )
    )
    if not item or (item.category == "automation_failure" and not user.is_operator):
        raise HTTPException(404, "Notification not found")
    return item


def present_notification(db, item):
    result = NotificationOut.model_validate(item)
    result.deliveries = [
        {
            "id": row.id,
            "channel": row.channel,
            "status": row.status,
            "attempts": row.attempts,
            "error_code": row.error_code,
            "delivered_at": row.delivered_at,
        }
        for row in db.scalars(
            select(NotificationOutbox)
            .where(NotificationOutbox.notification_id == item.id)
            .order_by(NotificationOutbox.channel)
        )
    ]
    return result


@router.get("/notifications")
def notifications(
    db: DB,
    user: CurrentUser,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    include_history: bool = False,
    unread_only: bool = False,
):
    query = select(Notification).where(Notification.user_id == user.id)
    if not user.is_operator:
        query = query.where(Notification.category != "automation_failure")
    unread = db.scalar(
        select(func.count()).select_from(
            query.where(
                Notification.in_app_status == "delivered", Notification.read_at.is_(None)
            ).subquery()
        )
    )
    if not include_history:
        query = query.where(Notification.in_app_status == "delivered")
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    result = paginate(
        db, query.order_by(Notification.created_at.desc(), Notification.id), page, page_size
    )
    result["items"] = [present_notification(db, n) for n in result["items"]]
    result["unread_count"] = unread
    return result


@router.post("/notifications/read-batch")
def read_batch(data: ReadBatch, db: DB, user: CurrentUser):
    items = [owned_notification(db, user, str(key)) for key in set(data.ids)]
    for item in items:
        item.read_at = item.read_at or utcnow()
    return {"marked_read": len(items)}


@router.get("/notifications/{notification_id}", response_model=NotificationOut)
def notification(notification_id: UUID, db: DB, user: CurrentUser):
    return present_notification(db, owned_notification(db, user, str(notification_id)))


@router.patch("/notifications/{notification_id}/read", response_model=NotificationOut)
def read(notification_id: UUID, data: ReadIn, db: DB, user: CurrentUser):
    item = owned_notification(db, user, str(notification_id))
    item.read_at = (item.read_at or utcnow()) if data.read else None
    return present_notification(db, item)


@router.get("/alerts", response_model=Page[AlertOut])
def alerts(db: DB, user: CurrentUser, page: PageNumber = 1, page_size: PageSize = 20):
    return service.alerts(db, user.id, page, page_size)


@router.post("/alerts", response_model=AlertOut, status_code=201)
def create_alert(data: AlertIn, db: DB, user: CurrentUser):
    return service.save_alert(db, user.id, data)


@router.put("/alerts/{alert_id}", response_model=AlertOut)
def update_alert(alert_id: UUID, data: AlertUpdate, db: DB, user: CurrentUser):
    return service.save_alert(db, user.id, data, str(alert_id))


@router.delete("/alerts/{alert_id}", status_code=204)
def delete_alert(alert_id: UUID, db: DB, user: CurrentUser):
    db.delete(service.owned_alert(db, user.id, str(alert_id), True))


@router.get("/alerts/{alert_id}/activity")
def alert_activity(
    alert_id: UUID, db: DB, user: CurrentUser, page: PageNumber = 1, page_size: PageSize = 20
):
    service.owned_alert(db, user.id, str(alert_id))
    # JSON containment is performed only on the already owned candidate's events.
    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import JSONB

    query = select(Notification).where(
        Notification.user_id == user.id,
        cast(Notification.subscription_ids, JSONB).contains([str(alert_id)]),
    )
    result = paginate(
        db, query.order_by(Notification.created_at.desc(), Notification.id), page, page_size
    )
    result["items"] = [present_notification(db, n) for n in result["items"]]
    return result


@router.get("/reminders", response_model=Page[ReminderOut])
def reminders(
    db: DB,
    user: CurrentUser,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    status: Literal["scheduled", "notified", "completed", "cancelled"] | None = None,
):
    return service.reminders(db, user.id, page, page_size, status)


@router.post("/reminders", response_model=ReminderOut, status_code=201)
def create_reminder(data: ReminderIn, db: DB, user: CurrentUser):
    return service.save_reminder(db, user.id, data)


@router.put("/reminders/{reminder_id}", response_model=ReminderOut)
def update_reminder(reminder_id: UUID, data: ReminderUpdate, db: DB, user: CurrentUser):
    return service.save_reminder(db, user.id, data, str(reminder_id))


@router.post("/reminders/{reminder_id}/action", response_model=ReminderOut)
def reminder_action(reminder_id: UUID, data: ReminderAction, db: DB, user: CurrentUser):
    return service.reminder_action(db, user.id, str(reminder_id), data)


@router.put("/automation/sources/{source_id}/schedule")
def source_schedule(source_id: UUID, data: SourceScheduleIn, db: DB, user: CurrentUser):
    operator(user)
    return configure_schedule(db, str(source_id), data)


@router.get("/automation/status")
def automation_status(db: DB, user: CurrentUser):
    operator(user)

    def counts(model):
        return dict(db.execute(select(model.status, func.count()).group_by(model.status)).all())

    beat = db.get(AutomationHeartbeat, "shared_worker")
    return {
        "enabled": settings.automation_enabled,
        "email_available": service.email_available(),
        "last_completed_tick_at": beat.last_tick_at if beat else None,
        "worker_required": True,
        "health_note": "API availability does not establish that the worker is running or supervised.",
        "task_counts": counts(AutomationTask),
        "outbox_counts": counts(NotificationOutbox),
        "pending_reminders": db.scalar(
            select(func.count())
            .select_from(ApplicationReminder)
            .where(ApplicationReminder.status == "scheduled")
        ),
        "due_reminders": db.scalar(
            select(func.count())
            .select_from(ApplicationReminder)
            .where(
                ApplicationReminder.status == "scheduled", ApplicationReminder.due_at <= utcnow()
            )
        ),
        "retrying_source_runs": db.scalar(
            select(func.count())
            .select_from(IngestionRun)
            .where(IngestionRun.retry_at.is_not(None), IngestionRun.retry_spawned.is_(False))
        ),
        "pending_task_oldest": db.scalar(
            select(func.min(AutomationTask.created_at)).where(
                AutomationTask.status.in_(["queued", "retry_scheduled"])
            )
        ),
    }


@router.get("/automation/tasks", response_model=Page[TaskOut])
def tasks(db: DB, user: CurrentUser, page: PageNumber = 1, page_size: PageSize = 20):
    operator(user)
    return paginate(
        db,
        select(AutomationTask).order_by(AutomationTask.created_at.desc(), AutomationTask.id),
        page,
        page_size,
    )


@router.post("/automation/tasks/{task_id}/retry", response_model=TaskOut)
def retry_task(task_id: UUID, db: DB, user: CurrentUser):
    operator(user)
    item = db.scalar(
        select(AutomationTask).where(AutomationTask.id == str(task_id)).with_for_update()
    )
    if not item:
        raise HTTPException(404, "Task not found")
    if item.status != "failed" or item.error_code not in {
        "database_unavailable",
        "worker_interrupted",
    }:
        raise HTTPException(409, "Only safely retryable failed tasks may be retried")
    item.status = "queued"
    item.retries = 0
    item.due_at = utcnow()
    item.finished_at = None
    return item


@router.post("/automation/deliveries/{outbox_id}/reconcile")
def reconcile(outbox_id: UUID, data: ReconcileIn, db: DB, user: CurrentUser):
    operator(user)
    item = db.scalar(
        select(NotificationOutbox).where(NotificationOutbox.id == str(outbox_id)).with_for_update()
    )
    if not item:
        raise HTTPException(404, "Delivery not found")
    if item.status != "uncertain":
        raise HTTPException(409, "Only uncertain deliveries require reconciliation")
    item.status = data.decision
    item.error_code = "operator_reconciled"
    if data.decision == "delivered":
        item.delivered_at = utcnow()
    db.add(
        AutomationTask(
            kind="email_reconciliation",
            dedupe_key="reconcile:" + item.id,
            status="completed",
            outcome={"decision": data.decision, "evidence": data.evidence, "operator_id": user.id},
            finished_at=utcnow(),
        )
    )
    return {
        "id": item.id,
        "status": item.status,
        "note": "Recorded operator reconciliation; no message was resent",
    }


@router.get("/automation/deliveries")
def deliveries(db: DB, user: CurrentUser, page: PageNumber = 1, page_size: PageSize = 20):
    operator(user)
    result = paginate(
        db,
        select(NotificationOutbox).order_by(
            NotificationOutbox.created_at.desc(), NotificationOutbox.id
        ),
        page,
        page_size,
    )
    result["items"] = [
        {
            "id": item.id,
            "channel": item.channel,
            "status": item.status,
            "attempts": item.attempts,
            "error_code": item.error_code,
            "due_at": item.due_at,
            "delivered_at": item.delivered_at,
            "history": [
                {
                    "number": a.number,
                    "status": a.status,
                    "error_code": a.error_code,
                    "started_at": a.started_at,
                    "finished_at": a.finished_at,
                }
                for a in db.scalars(
                    select(DeliveryAttempt)
                    .where(DeliveryAttempt.outbox_id == item.id)
                    .order_by(DeliveryAttempt.number)
                )
            ],
        }
        for item in result["items"]
    ]
    return result
