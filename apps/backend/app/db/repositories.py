from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Application, Job, Profile


def current_profile(db: Session, user_id: str) -> Profile:
    profile = db.scalar(select(Profile).where(Profile.user_id == user_id))
    if profile is None:
        raise HTTPException(404, "Create your candidate profile first")
    return profile


def job_by_id(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


def owned_application(db: Session, user_id: str, application_id: str, lock=False) -> Application:
    stmt = (
        select(Application)
        .join(Profile, Application.profile_id == Profile.id)
        .where(Application.id == application_id, Profile.user_id == user_id)
    )
    if lock:
        stmt = stmt.with_for_update(of=Application)
    item = db.scalar(stmt)
    if item is None:
        raise HTTPException(404, "Application not found")
    return item


def paginate(db: Session, stmt, page: int, page_size: int):
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    items = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).unique().all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}
