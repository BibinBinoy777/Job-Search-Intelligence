from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.schemas import PreferencesIn, ProfileEdit
from app.db.models import AuditEvent, CandidateSkill, Education, Experience, Preferences, Profile
from app.db.repositories import current_profile


def locked_profile(db, user_id):
    profile = current_profile(db, user_id)
    db.execute(select(Profile.id).where(Profile.id == profile.id).with_for_update())
    db.refresh(profile)
    return profile


def audit(db, user_id, action, resource_id=None):
    db.add(AuditEvent(user_id=user_id, action=action, resource_id=resource_id))


def create_profile(db: Session, user_id: str, data: ProfileEdit):
    if db.scalar(select(Profile.id).where(Profile.user_id == user_id)):
        raise HTTPException(409, "Profile already exists")
    p = Profile(user_id=user_id, **data.model_dump())
    db.add(p)
    db.flush()
    db.add(Preferences(profile_id=p.id))
    audit(db, user_id, "profile.created", p.id)
    db.flush()
    db.refresh(p)
    return p


def update_profile(db, user_id, data):
    p = locked_profile(db, user_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(p, key, value)
    audit(db, user_id, "profile.updated", p.id)
    db.flush()
    return p


def add_skill(db, user_id, data):
    p = locked_profile(db, user_id)
    normalized = data.name.casefold()
    db.execute(
        insert(CandidateSkill)
        .values(profile_id=p.id, name=data.name, normalized_name=normalized)
        .on_conflict_do_nothing(constraint="uq_candidate_skill")
    )
    audit(db, user_id, "skill.saved", p.id)
    return db.scalar(
        select(CandidateSkill).where(
            CandidateSkill.profile_id == p.id, CandidateSkill.normalized_name == normalized
        )
    )


CHILD_MODELS = {"experience": Experience, "education": Education, "skills": CandidateSkill}


def child(db, user_id, kind, item_id):
    p = locked_profile(db, user_id)
    model = CHILD_MODELS[kind]
    item = db.scalar(select(model).where(model.id == item_id, model.profile_id == p.id))
    if item is None:
        raise HTTPException(404, f"{kind.title()} record not found")
    return item


def save_child(db, user_id, kind, data, item_id=None):
    p = locked_profile(db, user_id)
    if item_id:
        item = child(db, user_id, kind, item_id)
        for key, value in data.model_dump().items():
            if key in {"is_current", "completion_status"} and key not in data.model_fields_set:
                continue
            setattr(item, key, value)
    else:
        item = CHILD_MODELS[kind](profile_id=p.id, **data.model_dump())
        db.add(item)
    audit(db, user_id, f"{kind}.saved", p.id)
    db.flush()
    return item


def delete_child(db, user_id, kind, item_id):
    item = child(db, user_id, kind, item_id)
    audit(db, user_id, f"{kind}.deleted", item.id)
    db.delete(item)


def update_preferences(db, user_id, data):
    p = locked_profile(db, user_id)
    item = db.get(Preferences, p.id)
    # PATCH is partial; validate merged fields so currency cannot be cleared under a salary.
    merged = (
        PreferencesIn.model_validate(item).model_dump() if item else PreferencesIn().model_dump()
    )
    merged.update(data.model_dump(exclude_unset=True))
    validated = PreferencesIn.model_validate(merged)
    if item is None:
        item = Preferences(profile_id=p.id)
        db.add(item)
    for key, value in validated.model_dump().items():
        setattr(item, key, value)
    audit(db, user_id, "preferences.updated", p.id)
    db.flush()
    return item
