from fastapi import HTTPException
from sqlalchemy import select

from app.api.schemas import ApplicationIn
from app.db.models import Application, ApplicationEvent
from app.db.repositories import current_profile, job_by_id, owned_application, paginate
from app.services.candidates import audit

TERMINAL = {"offer", "rejected", "withdrawn"}


def create_application(db, user_id, data):
    p = current_profile(db, user_id)
    job_by_id(db, data.job_id)
    if db.scalar(
        select(Application.id).where(
            Application.profile_id == p.id, Application.job_id == data.job_id
        )
    ):
        raise HTTPException(409, "This job is already in your application tracker")
    item = Application(profile_id=p.id, **data.model_dump())
    db.add(item)
    db.flush()
    db.add(ApplicationEvent(application_id=item.id, from_status=None, to_status=item.status))
    audit(db, user_id, "application.created", item.id)
    db.flush()
    db.refresh(item)
    return item


def update_application(db, user_id, application_id, data):
    item = owned_application(db, user_id, application_id, lock=True)
    if item.version != data.expected_version:
        raise HTTPException(409, "Application changed. Refresh before saving again")
    values = data.model_dump(exclude_unset=True, exclude={"expected_version", "correction_reason"})
    if "status" in values and values["status"] is None:
        raise HTTPException(422, "Status cannot be null")
    merged = ApplicationIn.model_validate(item).model_dump()
    merged.update(values)
    ApplicationIn.model_validate(merged)
    new_status = values.get("status", item.status)
    if new_status != item.status:
        if item.status in TERMINAL and not data.correction_reason:
            raise HTTPException(422, "Changing an outcome requires a correction reason")
        db.add(
            ApplicationEvent(
                application_id=item.id,
                from_status=item.status,
                to_status=new_status,
                reason=data.correction_reason,
            )
        )
    for key, value in values.items():
        setattr(item, key, value)
    if new_status == "withdrawn":
        from app.core.security import utcnow
        from app.db.models import ApplicationReminder

        for reminder in db.scalars(
            select(ApplicationReminder)
            .where(
                ApplicationReminder.application_id == item.id,
                ApplicationReminder.status.in_(["scheduled", "notified"]),
            )
            .with_for_update()
        ):
            reminder.status = "cancelled"
            reminder.revision += 1
            reminder.updated_at = utcnow()
    audit(db, user_id, "application.updated", item.id)
    db.flush()
    return item


def list_applications(db, user_id, page, page_size):
    p = current_profile(db, user_id)
    return paginate(
        db,
        select(Application)
        .where(Application.profile_id == p.id)
        .order_by(Application.updated_at.desc(), Application.id),
        page,
        page_size,
    )


def application_events(db, user_id, application_id, page, page_size):
    owned_application(db, user_id, application_id)
    return paginate(
        db,
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == application_id)
        .order_by(ApplicationEvent.created_at, ApplicationEvent.id),
        page,
        page_size,
    )
