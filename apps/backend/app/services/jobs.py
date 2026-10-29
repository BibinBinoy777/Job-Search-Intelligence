from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.api.schemas import JobIn, JobOut, SavedOut
from app.core.security import utcnow
from app.db.models import Job, JobSkill, JobSource, Profile, SavedJob
from app.db.repositories import current_profile, job_by_id, paginate


def store_job(db, data: JobIn):
    """Trusted CLI/adapter boundary, never exposed as a candidate write API.

    Serialize repeated source deliveries using the unique source identity and a row
    lock. Unknown identities stay separate rather than guessing title equivalence.
    """
    payload = data.model_dump(exclude={"skills"})
    if payload["source_url"] is not None:
        payload["source_url"] = str(payload["source_url"])
    if data.source_id:
        source = db.get(JobSource, data.source_id)
        if source is None:
            raise ValueError("Job source does not exist")
        if source.adapter_key:
            raise ValueError("Use the ingestion pipeline to write records for an integrated source")
    if data.external_id:
        db.execute(
            insert(Job)
            .values(**payload)
            .on_conflict_do_nothing(constraint="uq_job_source_identity")
        )
        item = db.scalar(
            select(Job)
            .where(Job.source_id == data.source_id, Job.external_id == data.external_id)
            .with_for_update(of=Job)
        )
        previous = JobIn.model_validate(item).model_dump(exclude={"skills"})
        if previous["source_url"] is not None:
            previous["source_url"] = str(previous["source_url"])
        changed = any(previous[k] != v for k, v in payload.items() if k != "last_verified_at")
        old_skills = {(s.normalized_name, s.kind) for s in item.skills}
        new_skills = {(s.name.casefold(), s.kind) for s in data.skills}
        if changed or old_skills != new_skills:
            item.material_updated_at = utcnow()
        for key, value in payload.items():
            setattr(item, key, value)
        item.last_seen_at = utcnow()
    else:
        item = Job(**payload)
        db.add(item)
        db.flush()
    item.skills.clear()
    db.flush()
    seen = set()
    for skill in data.skills:
        key = (skill.name.casefold(), skill.kind)
        if key not in seen:
            item.skills.append(JobSkill(name=skill.name, normalized_name=key[0], kind=skill.kind))
            seen.add(key)
    db.flush()
    return item


def present_job(db, user_id, item):
    result = JobOut.model_validate(item)
    result.is_saved = bool(
        db.scalar(
            select(SavedJob.id)
            .join(Profile, SavedJob.profile_id == Profile.id)
            .where(Profile.user_id == user_id, SavedJob.job_id == item.id)
        )
    )
    return result


def list_jobs(db, user_id, params):
    # Single canonical discovery entry point, extended by Phase 4.
    from app.modules.search.service import search

    return search(db, user_id, params)


def save_job(db, user_id, job_id):
    p = current_profile(db, user_id)
    job_by_id(db, job_id)
    db.execute(
        insert(SavedJob)
        .values(profile_id=p.id, job_id=job_id)
        .on_conflict_do_nothing(constraint="uq_saved_job")
    )
    return {"saved": True}


def unsave_job(db, user_id, job_id):
    p = current_profile(db, user_id)
    job_by_id(db, job_id)
    item = db.scalar(select(SavedJob).where(SavedJob.profile_id == p.id, SavedJob.job_id == job_id))
    if item:
        db.delete(item)


def saved_jobs(db, user_id, page, page_size):
    p = current_profile(db, user_id)
    result = paginate(
        db,
        select(SavedJob)
        .where(SavedJob.profile_id == p.id)
        .order_by(SavedJob.created_at.desc(), SavedJob.id),
        page,
        page_size,
    )
    result["items"] = [SavedOut.model_validate(item) for item in result["items"]]
    for item in result["items"]:
        item.job.is_saved = True
    return result
