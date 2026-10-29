from fastapi import HTTPException
from sqlalchemy import func, select, text, union_all

from app.api.schemas import JobOut
from app.core.security import utcnow
from app.db.models import Job, JobSkill, Profile, SavedJob, SavedSearch
from app.db.repositories import current_profile, job_by_id, paginate
from app.ingestion.control import lock_key
from app.ingestion.freshness import visible_job_condition
from app.modules.matching import service as matching
from app.modules.matching.representations import job_snapshot
from app.modules.matching.requirements import analyze_requirements
from app.modules.search.query import build_query
from app.modules.search.schemas import SearchCriteria, normalize_query


def search(db, user_id, params):
    stmt = build_query(db, user_id, params)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = (
        db.execute(stmt.limit(params.page_size).offset((params.page - 1) * params.page_size))
        .unique()
        .all()
    )
    ids = [row[0].id for row in rows]
    saved = (
        set(
            db.scalars(
                select(SavedJob.job_id)
                .join(Profile, Profile.id == SavedJob.profile_id)
                .where(Profile.user_id == user_id, SavedJob.job_id.in_(ids))
            )
        )
        if ids
        else set()
    )
    assessments, lexical, items = {}, {}, []
    for row in rows:
        job, data = row[0], row._mapping
        items.append(JobOut.model_validate(job).model_copy(update={"is_saved": job.id in saved}))
        lexical[job.id] = data["text_rank"]
        state = (
            "not_calculated"
            if data["match_id"] is None
            else "current"
            if data["is_current"]
            else "stale"
        )
        assessments[job.id] = {
            "state": state,
            "score": data["score"] if state == "current" else None,
            "eligibility": data["eligibility_status"] if state == "current" else None,
            "assessment_status": data["assessment_status"] if state == "current" else None,
            "required_coverage": data["required_coverage"] if state == "current" else None,
            "ranking_version": data["ranking_version"],
        }
    return {
        "items": items,
        "total": total,
        "page": params.page,
        "page_size": params.page_size,
        "assessments": assessments,
        "text_relevance": lexical,
        "notices": [
            "Text relevance measures query overlap, not candidate suitability. Matching quality has not been independently validated.",
            "Salary thresholds exclude unknown bounds and require the selected currency and period; no conversion is performed.",
            "Candidate score and coverage filters use only current assessments. Missing and stale assessments do not count as zero.",
            "Integrated listings require recent verification by default. All listing states is a deliberate historical view; unavailable content stays suppressed.",
        ],
    }


def suggestions(db, q, limit):
    q = normalize_query(q)
    if len(q) < 2:
        return {"items": []}
    parts = []
    from sqlalchemy import literal

    for kind, column in [
        ("title", Job.title),
        ("employer", Job.employer),
        ("location", Job.location),
    ]:
        parts.append(
            select(literal(kind).label("kind"), column.label("value"))
            .where(
                visible_job_condition(),
                Job.status.not_in(["closed", "expired"]),
                column.icontains(q, autoescape=True),
            )
            .distinct()
        )
    parts.append(
        select(literal("skill").label("kind"), JobSkill.name.label("value"))
        .join(Job, Job.id == JobSkill.job_id)
        .where(
            visible_job_condition(),
            Job.status.not_in(["closed", "expired"]),
            JobSkill.name.icontains(q, autoescape=True),
        )
        .distinct()
    )
    values = union_all(*parts).subquery()
    rows = (
        db.execute(
            select(values.c.kind, values.c.value)
            .order_by(values.c.kind, func.lower(values.c.value).collate("C"), values.c.value)
            .limit(limit)
        )
        .mappings()
        .all()
    )
    return {"items": rows}


def compare(db, user_id, data):
    profile = db.scalar(select(Profile.id).where(Profile.user_id == user_id))
    items = []
    # Deliberately bounded to <= 3. Reuse source presentation and the existing
    # private pair service rather than inventing a comparison-specific ranker.
    from app.services.jobs import present_job

    for job_id in data.job_ids:
        job = job_by_id(db, str(job_id))
        public = present_job(db, user_id, job)
        available = public.is_available and job.status not in {"closed", "expired"}
        items.append(
            {
                "job": public,
                "requirements": analyze_requirements(job_snapshot(job)) if available else None,
                "candidate_assessment": matching.pair(db, user_id, job.id) if profile else None,
            }
        )
    return {"items": items, "limit": 3}


def saved_list(db, user_id, page, page_size):
    profile = current_profile(db, user_id)
    return paginate(
        db,
        select(SavedSearch)
        .where(SavedSearch.profile_id == profile.id)
        .order_by(SavedSearch.created_at.desc(), SavedSearch.id),
        page,
        page_size,
    )


def owned_search(db, user_id, search_id):
    profile = current_profile(db, user_id)
    item = db.scalar(
        select(SavedSearch).where(SavedSearch.id == search_id, SavedSearch.profile_id == profile.id)
    )
    if item is None:
        raise HTTPException(404, "Saved search not found")
    return item


def save_search(db, user_id, data):
    profile = current_profile(db, user_id)
    db.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": lock_key("saved-searches:" + profile.id)},
    )
    if (
        db.scalar(
            select(func.count())
            .select_from(SavedSearch)
            .where(SavedSearch.profile_id == profile.id)
        )
        >= 50
    ):
        raise HTTPException(409, "At most 50 saved searches are supported")
    item = SavedSearch(
        profile_id=profile.id,
        name=data.name,
        normalized_name=data.name.casefold(),
        criteria=data.criteria.model_dump(mode="json"),
    )
    db.add(item)
    db.flush()
    return item


def update_search(db, user_id, search_id, data):
    item = owned_search(db, user_id, search_id)
    if data.name is not None:
        item.name, item.normalized_name = data.name, data.name.casefold()
    if data.criteria is not None:
        item.criteria = data.criteria.model_dump(mode="json")
    db.flush()
    return item


def use_search(db, user_id, search_id):
    item = owned_search(db, user_id, search_id)
    # Revalidate persisted definitions on load (including future schema drift).
    item.criteria = SearchCriteria.model_validate(item.criteria).model_dump(mode="json")
    item.last_used_at = utcnow()
    db.flush()
    return item
