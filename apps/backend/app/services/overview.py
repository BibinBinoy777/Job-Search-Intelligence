from sqlalchemy import func, select

from app.api.schemas import ApplicationOut, EventOut
from app.db.models import Application, ApplicationEvent, Profile, SavedJob


def overview(db, user_id):
    p = db.scalar(select(Profile).where(Profile.user_id == user_id))
    if not p:
        return {
            "completion": 0,
            "completed_fields": 0,
            "total_fields": 8,
            "saved_count": 0,
            "application_count": 0,
            "recent_activity": [],
            "recent_applications": [],
        }
    fields = [
        bool(p.name),
        bool(p.headline),
        bool(p.summary),
        bool(p.skills),
        bool(p.experience),
        bool(p.education),
        bool(p.projects),
        bool(p.preferences and p.preferences.target_titles),
    ]
    saved_count = db.scalar(
        select(func.count()).select_from(SavedJob).where(SavedJob.profile_id == p.id)
    )
    application_count = db.scalar(
        select(func.count()).select_from(Application).where(Application.profile_id == p.id)
    )
    recent = db.scalars(
        select(Application)
        .where(Application.profile_id == p.id)
        .order_by(Application.updated_at.desc())
        .limit(5)
    ).all()
    events = db.scalars(
        select(ApplicationEvent)
        .join(Application, ApplicationEvent.application_id == Application.id)
        .where(Application.profile_id == p.id)
        .order_by(ApplicationEvent.created_at.desc())
        .limit(8)
    ).all()
    return {
        "completion": round(sum(fields) / len(fields) * 100),
        "completed_fields": sum(fields),
        "total_fields": len(fields),
        "saved_count": saved_count,
        "application_count": application_count,
        "recent_activity": [EventOut.model_validate(e) for e in events],
        "recent_applications": [ApplicationOut.model_validate(a) for a in recent],
    }
