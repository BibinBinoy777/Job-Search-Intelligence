from datetime import UTC, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import func, select, text

from app.core.config import settings
from app.core.security import utcnow
from app.db.models import (
    AlertSubscription,
    ApplicationReminder,
    AutomationTask,
    NotificationPreference,
    SavedSearch,
)
from app.db.repositories import current_profile, owned_application, paginate
from app.ingestion.control import lock_key
from app.modules.automation.schemas import AlertOut, NotificationPreferencesIn
from app.modules.search.schemas import SearchCriteria


def email_available():
    return bool(settings.smtp_host and settings.smtp_sender)


def preferences(db, user_id):
    item = db.get(NotificationPreference, user_id)
    return NotificationPreferencesIn.model_validate(item) if item else NotificationPreferencesIn()


def put_preferences(db, user_id, data):
    if data.email and not email_available():
        raise HTTPException(
            422, "Email delivery is not configured; in-app notifications remain available"
        )
    item = db.get(NotificationPreference, user_id)
    if not item:
        item = NotificationPreference(user_id=user_id)
        db.add(item)
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    db.flush()
    return preferences(db, user_id)


def owned_alert(db, user_id, alert_id, lock=False):
    profile = current_profile(db, user_id)
    query = select(AlertSubscription).where(
        AlertSubscription.id == alert_id, AlertSubscription.profile_id == profile.id
    )
    if lock:
        query = query.with_for_update()
    item = db.scalar(query)
    if not item:
        raise HTTPException(404, "Alert subscription not found")
    return item


def save_alert(db, user_id, data, alert_id=None):
    profile = current_profile(db, user_id)
    if data.email and not email_available():
        raise HTTPException(422, "Email delivery is not configured")
    criteria = data.criteria
    if data.saved_search_id:
        saved = db.scalar(
            select(SavedSearch).where(
                SavedSearch.id == str(data.saved_search_id), SavedSearch.profile_id == profile.id
            )
        )
        if not saved:
            raise HTTPException(404, "Saved search not found")
        if "criteria" not in data.model_fields_set:
            criteria = SearchCriteria.model_validate(saved.criteria)
    # Revalidate copied searches too: historical/stale criteria cannot issue alerts.
    if (
        criteria.availability_scope != "available"
        or criteria.status in {"unknown", "closed", "expired"}
        or criteria.match_state in {"stale", "missing", "insufficient"}
    ):
        raise HTTPException(
            422,
            "Alerts require active available listings and current assessments for score conditions",
        )
    if alert_id:
        item = owned_alert(db, user_id, alert_id, True)
        if item.revision != data.expected_revision:
            raise HTTPException(409, "Subscription changed; reload before editing")
        item.revision += 1
    else:
        db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": lock_key("alert-quota:" + profile.id)},
        )
        if (
            db.scalar(
                select(func.count())
                .select_from(AlertSubscription)
                .where(AlertSubscription.profile_id == profile.id)
            )
            >= 50
        ):
            raise HTTPException(409, "At most 50 alert subscriptions per candidate are supported")
        item = AlertSubscription(profile_id=profile.id)
        db.add(item)
    item.name, item.normalized_name = data.name, data.name.casefold()
    item.criteria = criteria.model_dump(mode="json")
    item.saved_search_id = str(data.saved_search_id) if data.saved_search_id else None
    item.enabled, item.include_updates, item.email = data.enabled, data.include_updates, data.email
    # Edits/resume deliberately start a new future-only window, never a backlog.
    item.starts_after = utcnow()
    db.flush()
    return AlertOut.model_validate(item)


def alerts(db, user_id, page, page_size):
    profile = current_profile(db, user_id)
    return paginate(
        db,
        select(AlertSubscription)
        .where(AlertSubscription.profile_id == profile.id)
        .order_by(AlertSubscription.created_at.desc(), AlertSubscription.id),
        page,
        page_size,
    )


def local_instant(local_time, zone_name, fold=None):
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, "Choose a valid IANA timezone") from None
    possible = {}
    for occurrence in [0, 1]:
        value = local_time.replace(tzinfo=zone, fold=occurrence).astimezone(UTC)
        if value.astimezone(zone).replace(tzinfo=None) == local_time:
            possible[occurrence] = value
    if not possible:
        raise HTTPException(422, "This local time does not exist during the daylight-saving change")
    if len(set(possible.values())) > 1 and fold is None:
        raise HTTPException(
            422, "This local time occurs twice; explicitly choose first or second occurrence"
        )
    value = possible.get(fold if fold is not None else 0)
    if value is None:
        raise HTTPException(422, "Invalid local-time occurrence")
    if value > utcnow() + timedelta(days=5 * 366):
        raise HTTPException(422, "Reminders can be scheduled up to five years ahead")
    return value


def owned_reminder(db, user_id, reminder_id, lock=False):
    profile = current_profile(db, user_id)
    query = select(ApplicationReminder).where(
        ApplicationReminder.id == reminder_id, ApplicationReminder.profile_id == profile.id
    )
    if lock:
        query = query.with_for_update()
    item = db.scalar(query)
    if not item:
        raise HTTPException(404, "Application reminder not found")
    return item


def save_reminder(db, user_id, data, reminder_id=None):
    profile = current_profile(db, user_id)
    app = owned_application(db, user_id, str(data.application_id), lock=True)
    if app.status == "withdrawn":
        raise HTTPException(409, "Withdrawn applications cannot have pending reminders")
    if data.email and not email_available():
        raise HTTPException(422, "Email delivery is not configured")
    due = local_instant(data.local_time, data.timezone, data.fold)
    if reminder_id:
        item = owned_reminder(db, user_id, reminder_id, True)
        if item.application_id != app.id:
            raise HTTPException(422, "A reminder cannot be moved to another application")
        if item.revision != data.expected_revision:
            raise HTTPException(409, "Reminder changed; reload before editing")
        if item.status in {"cancelled", "completed"}:
            raise HTTPException(409, "Create a new reminder after completion or cancellation")
        item.revision += 1
    else:
        db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": lock_key("reminder-quota:" + profile.id)},
        )
        if (
            db.scalar(
                select(func.count())
                .select_from(ApplicationReminder)
                .where(
                    ApplicationReminder.profile_id == profile.id,
                    ApplicationReminder.status.in_(["scheduled", "notified"]),
                )
            )
            >= 100
        ):
            raise HTTPException(409, "At most 100 active reminders are supported")
        item = ApplicationReminder(profile_id=profile.id, application_id=app.id, revision=1)
        db.add(item)
    item.kind, item.due_at, item.timezone, item.note, item.email = (
        data.kind,
        due,
        data.timezone,
        data.note,
        data.email,
    )
    item.status = "scheduled"
    db.flush()
    db.add(
        AutomationTask(
            kind="reminder",
            reminder_id=item.id,
            reminder_revision=item.revision,
            dedupe_key=f"reminder:{item.id}:{item.revision}",
            due_at=due,
        )
    )
    db.flush()
    return item


def reminder_action(db, user_id, reminder_id, data):
    item = owned_reminder(db, user_id, reminder_id, True)
    status = "completed" if data.action == "complete" else "cancelled"
    if item.status == status:
        return item
    if item.revision != data.expected_revision:
        raise HTTPException(409, "Reminder changed; reload before editing")
    item.status = status
    item.revision += 1
    item.completed_at = utcnow() if status == "completed" else None
    db.flush()
    return item


def reminders(db, user_id, page, page_size, status=None):
    profile = current_profile(db, user_id)
    query = select(ApplicationReminder).where(ApplicationReminder.profile_id == profile.id)
    if status:
        query = query.where(ApplicationReminder.status == status)
    return paginate(
        db, query.order_by(ApplicationReminder.due_at, ApplicationReminder.id), page, page_size
    )
