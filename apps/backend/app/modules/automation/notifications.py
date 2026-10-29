from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.security import utcnow
from app.db.models import (
    AlertSubscription,
    Application,
    ApplicationReminder,
    Job,
    JobEvent,
    Notification,
    NotificationOutbox,
    Profile,
    User,
)
from app.modules.automation.events import content_version
from app.modules.automation.service import preferences
from app.modules.search.query import build_query
from app.modules.search.schemas import SearchParams


def eligible(job, now=None):
    now = now or utcnow()
    return bool(
        job
        and job.status == "active"
        and job.last_verified_at
        and job.last_verified_at >= now - timedelta(hours=24)
        and (job.source_expires_at is None or job.source_expires_at > now)
    )


def matches(db, user_id, subscription, job_id):
    params = SearchParams.model_validate(subscription.criteria)
    row = (
        db.execute(build_query(db, user_id, params).where(Job.id == job_id).limit(1))
        .unique()
        .first()
    )
    if row is None:
        return False
    if any(
        value is not None
        for value in [params.minimum_score, params.required_coverage, params.eligibility]
    ):
        return bool(
            row.is_current and row.assessment_status == "assessed" and row.score is not None
        )
    return True


def create_notification(db, *, user_id, key, category, title, message, href, email=False, **refs):
    inserted = db.scalar(
        insert(Notification)
        .values(
            user_id=user_id,
            dedupe_key=key,
            category=category,
            title=title,
            message=message,
            href=href,
            **refs,
        )
        .on_conflict_do_nothing(constraint="uq_notification_event")
        .returning(Notification.id)
    )
    item = db.scalar(select(Notification).where(Notification.dedupe_key == key).with_for_update())
    if inserted:
        prefs = preferences(db, user_id)
        if prefs.in_app:
            db.add(NotificationOutbox(notification_id=item.id, channel="in_app"))
        else:
            item.in_app_status = "suppressed"
        if email and prefs.email:
            db.add(NotificationOutbox(notification_id=item.id, channel="email"))
    db.flush()
    return item, bool(inserted)


def evaluate_event(db, task):
    event = db.get(JobEvent, task.event_id)
    job = db.get(Job, event.job_id) if event else None
    if not event or not eligible(job) or event.content_fingerprint != content_version(job):
        return True, {"excluded": 1, "reason": "listing_unavailable_or_event_superseded"}
    cursor = (task.payload or {}).get("after_subscription", "")
    subs = db.scalars(
        select(AlertSubscription)
        .where(
            AlertSubscription.id > cursor,
            AlertSubscription.enabled.is_(True),
            AlertSubscription.starts_after < event.created_at,
        )
        .order_by(AlertSubscription.id)
        .limit(51)
    ).all()
    created = matched = 0
    for sub in subs[:50]:
        if event.kind == "material_update" and not sub.include_updates:
            continue
        profile = db.get(Profile, sub.profile_id)
        if not profile or not preferences(db, profile.user_id).job_alerts:
            continue
        if not matches(db, profile.user_id, sub, job.id):
            continue
        matched += 1
        notification, new = create_notification(
            db,
            user_id=profile.user_id,
            key=f"job:{event.id}:{profile.user_id}",
            category=event.kind,
            title="New listing observed"
            if event.kind == "new_listing"
            else "Listing materially updated",
            message=job.title,
            href=f"/jobs/{job.id}",
            email=sub.email,
            job_id=job.id,
            event_id=event.id,
            subscription_ids=[sub.id],
        )
        created += new
        if sub.id not in notification.subscription_ids:
            notification.subscription_ids = [*notification.subscription_ids, sub.id]
        if sub.email and preferences(db, profile.user_id).email:
            db.execute(
                insert(NotificationOutbox)
                .values(notification_id=notification.id, channel="email")
                .on_conflict_do_nothing(constraint="uq_notification_channel")
            )
    more = len(subs) > 50
    if more:
        task.payload = {"after_subscription": subs[49].id}
    previous = task.outcome or {}
    return not more, {
        "created": previous.get("created", 0) + created,
        "matching_subscriptions": previous.get("matching_subscriptions", 0) + matched,
    }


def process_reminder(db, task):
    reminder = db.scalar(
        select(ApplicationReminder)
        .where(ApplicationReminder.id == task.reminder_id)
        .with_for_update()
    )
    if (
        not reminder
        or reminder.revision != task.reminder_revision
        or reminder.status != "scheduled"
    ):
        return True, {"cancelled": 1}
    app = db.get(Application, reminder.application_id)
    if not app or app.status == "withdrawn":
        reminder.status = "cancelled"
        return True, {"cancelled": 1}
    if reminder.due_at > utcnow():
        task.due_at = reminder.due_at
        return False, {"not_due": 1}
    profile = db.get(Profile, reminder.profile_id)
    if not preferences(db, profile.user_id).reminders:
        # Suppressed due reminders stay scheduled; task is delayed, not falsely delivered.
        task.due_at = utcnow() + timedelta(minutes=5)
        return False, {"preferences_paused": 1}
    create_notification(
        db,
        user_id=profile.user_id,
        key=f"reminder:{reminder.id}:{reminder.revision}",
        category="application_reminder",
        title="Application reminder",
        message=f"{reminder.kind.replace('_', ' ')} is due. Open your application to review your note and next action.",
        href=f"/applications?open={app.id}",
        email=reminder.email,
        application_id=app.id,
        reminder_id=reminder.id,
        reminder_revision=reminder.revision,
    )
    reminder.status = "notified"
    return True, {"created": 1}


def permitted_delivery(db, notification, channel):
    prefs = preferences(db, notification.user_id)
    if (channel == "in_app" and not prefs.in_app) or (channel == "email" and not prefs.email):
        return False
    if notification.category in {"new_listing", "material_update"}:
        job = db.get(Job, notification.job_id) if notification.job_id else None
        event = db.get(JobEvent, notification.event_id) if notification.event_id else None
        if (
            not prefs.job_alerts
            or not eligible(job)
            or not event
            or content_version(job) != event.content_fingerprint
        ):
            return False
        profile = db.scalar(select(Profile).where(Profile.user_id == notification.user_id))
        if not profile:
            return False
        subs = db.scalars(
            select(AlertSubscription).where(
                AlertSubscription.id.in_(notification.subscription_ids),
                AlertSubscription.profile_id == profile.id,
                AlertSubscription.enabled.is_(True),
            )
        ).all()
        return any(
            sub.starts_after < event.created_at
            and (channel != "email" or sub.email)
            and matches(db, notification.user_id, sub, job.id)
            for sub in subs
        )
    if notification.category == "application_reminder":
        reminder = (
            db.get(ApplicationReminder, notification.reminder_id)
            if notification.reminder_id
            else None
        )
        app = (
            db.get(Application, notification.application_id)
            if notification.application_id
            else None
        )
        return bool(
            prefs.reminders
            and reminder
            and reminder.revision == notification.reminder_revision
            and reminder.status == "notified"
            and app
            and app.status != "withdrawn"
            and (channel != "email" or reminder.email)
        )
    user = db.get(User, notification.user_id)
    return bool(user and user.is_operator)


def operator_failure(db, key, message, run_id=None):
    for user in db.scalars(select(User).where(User.is_operator.is_(True)).limit(50)):
        create_notification(
            db,
            user_id=user.id,
            key=f"operator:{key}:{user.id}",
            category="automation_failure",
            title="Automation needs attention",
            message=message,
            href="/sources",
            run_id=run_id,
        )
