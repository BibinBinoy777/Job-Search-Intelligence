"""Database-side lexical retrieval and exact current-assessment selection."""

from datetime import timedelta

from sqlalchemy import (
    DateTime,
    Float,
    String,
    and_,
    case,
    cast,
    false,
    func,
    literal,
    or_,
    select,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by

from app.core.security import utcnow
from app.db.models import Job, JobRequirementAnalysis, JobSkill, JobSource, MatchResult, Profile
from app.ingestion.freshness import visible_job_condition
from app.modules.matching.config import CONFIG
from app.modules.matching.representations import candidate_snapshot, fingerprint

# Kept in one place: weights describe lexical query relevance, never suitability.
TEXT_WEIGHTS = {
    "exact_title": 120,
    "title_phrase": 60,
    "title_term": 20,
    "employer_term": 12,
    "skill_term": 10,
    "responsibility_term": 5,
    "description_term": 2,
    "location_term": 2,
    "source_term": 1,
}


def normalized(column):
    return func.trim(
        func.regexp_replace(func.lower(func.coalesce(column, "")), r"[^[:alnum:]_+#.]+", " ", "g")
    )


def public_snapshot_sql():
    skills = (
        select(
            func.jsonb_agg(
                aggregate_order_by(
                    func.jsonb_build_object("name", JobSkill.name, "kind", JobSkill.kind),
                    JobSkill.kind.collate("C"),
                    JobSkill.name.collate("C"),
                )
            )
        )
        .where(JobSkill.job_id == Job.id)
        .correlate(Job)
        .scalar_subquery()
    )
    names = [
        "title",
        "description",
        "responsibilities",
        "qualifications",
        "experience_min",
        "experience_max",
        "employment_type",
        "work_arrangement",
        "location",
        "salary_min",
        "salary_max",
        "salary_currency",
        "salary_period",
        "location_restrictions",
        "timezone_restrictions",
        "source_categories",
    ]
    args = [part for name in names for part in (name, getattr(Job, name))]
    return func.jsonb_build_object(
        *args, "skills", func.coalesce(skills, cast(literal("[]"), JSONB))
    )


def current_analysis():
    return (
        select(JobRequirementAnalysis.analysis.label("analysis"))
        .select_from(JobRequirementAnalysis)
        .where(
            JobRequirementAnalysis.job_id == Job.id,
            JobRequirementAnalysis.extractor_version == CONFIG.extractor_version,
            cast(JobRequirementAnalysis.job_snapshot, JSONB) == public_snapshot_sql(),
        )
        .order_by(JobRequirementAnalysis.id)
        .limit(1)
        .correlate(Job)
        .lateral("requirements")
    )


def private_match(db, user_id, now):
    profile = db.scalar(select(Profile).where(Profile.user_id == user_id))
    candidate_fp = fingerprint(candidate_snapshot(profile)) if profile else None
    context = MatchResult.job_context
    current = (
        and_(
            MatchResult.candidate_fingerprint == candidate_fp,
            MatchResult.ranking_version == CONFIG.identity,
            MatchResult.config_fingerprint == CONFIG.fingerprint,
            MatchResult.assessment_day == now.date(),
            cast(JobRequirementAnalysis.job_snapshot, JSONB) == public_snapshot_sql(),
            JobRequirementAnalysis.extractor_version == CONFIG.extractor_version,
            *[
                context[key].as_string().is_not_distinct_from(getattr(Job, key))
                for key in ["status", "status_basis", "source_id", "external_id"]
            ],
            *[
                cast(context[key].as_string(), DateTime(timezone=True)).is_not_distinct_from(
                    getattr(Job, key)
                )
                for key in ["last_verified_at", "source_expires_at"]
            ],
            Job.status.not_in(["closed", "expired"]),
            or_(Job.source_expires_at.is_(None), Job.source_expires_at > now),
            visible_job_condition(now),
        )
        if profile
        else false()
    )
    return (
        select(
            MatchResult.id.label("match_id"),
            MatchResult.score,
            MatchResult.eligibility_status,
            MatchResult.assessment_status,
            MatchResult.ranking_version,
            cast(
                MatchResult.result["features"]["required_skills"]["value"].as_string(), Float
            ).label("required_coverage"),
            func.coalesce(current, false()).label("is_current"),
        )
        .select_from(MatchResult)
        .join(JobRequirementAnalysis, JobRequirementAnalysis.id == MatchResult.analysis_id)
        .where(
            MatchResult.profile_id == (profile.id if profile else ""), MatchResult.job_id == Job.id
        )
        .order_by(
            func.coalesce(current, false()).desc(),
            MatchResult.generated_at.desc(),
            MatchResult.id.desc(),
        )
        .limit(1)
        .correlate(Job)
        .lateral("own_match")
    )


def skill_text_exists(analysis, term):
    # Only required/preferred names/keys, never arbitrary JSON metadata/evidence.
    array = func.coalesce(cast(analysis["required_skills"], JSONB), cast(literal("[]"), JSONB)).op(
        "||"
    )(func.coalesce(cast(analysis["preferred_skills"], JSONB), cast(literal("[]"), JSONB)))
    entries = func.jsonb_array_elements(array).table_valued("value").alias("skill_entries")
    value = cast(entries.c.value, JSONB)
    return or_(
        select(JobSkill.id)
        .where(
            JobSkill.job_id == Job.id, normalized(JobSkill.name).icontains(term, autoescape=True)
        )
        .correlate(Job)
        .exists(),
        select(literal(1))
        .select_from(entries)
        .where(
            or_(
                normalized(value["name"].as_string()).icontains(term, autoescape=True),
                normalized(value["key"].as_string()).icontains(
                    term.replace(" ", "_"), autoescape=True
                ),
            )
        )
        .exists(),
    )


def build_query(db, user_id, params, now=None):
    now = now or utcnow()
    analysis = current_analysis()
    match = private_match(db, user_id, now)
    # Align status predicates with canonical JobOut presentation: an elapsed
    # integrated-source deadline is displayed as expired without rewriting rows.
    integrated = Job.source_id.in_(select(JobSource.id).where(JobSource.adapter_key.is_not(None)))
    display_status = case(
        (and_(integrated, Job.source_expires_at <= now), "expired"), else_=Job.status
    )
    stmt = select(Job).select_from(Job).outerjoin(analysis, true()).outerjoin(match, true())
    if params.availability_scope == "available":
        stmt = stmt.where(visible_job_condition(now))
    elif params.availability_scope == "requires_verification":
        stmt = stmt.where(
            display_status.not_in(["closed", "expired"]),
            or_(Job.last_verified_at.is_(None), Job.last_verified_at < now - timedelta(hours=24)),
        )
    rank = literal(0)
    if params.q:
        title, employer = normalized(Job.title), normalized(Job.employer)
        rank = case((title == params.q, TEXT_WEIGHTS["exact_title"]), else_=0) + case(
            (title.icontains(params.q, autoescape=True), TEXT_WEIGHTS["title_phrase"]), else_=0
        )
        for term in dict.fromkeys(params.q.split()):
            hits = {
                "title_term": title.icontains(term, autoescape=True),
                "employer_term": employer.icontains(term, autoescape=True),
                "skill_term": skill_text_exists(analysis.c.analysis, term),
                "responsibility_term": or_(
                    normalized(Job.responsibilities).icontains(term, autoescape=True),
                    normalized(Job.qualifications).icontains(term, autoescape=True),
                ),
                "description_term": normalized(Job.description).icontains(term, autoescape=True),
                "location_term": normalized(Job.location).icontains(term, autoescape=True),
                "source_term": or_(
                    select(JobSource.id)
                    .where(
                        JobSource.id == Job.source_id,
                        normalized(JobSource.name).icontains(term, autoescape=True),
                    )
                    .exists(),
                    normalized(cast(Job.source_categories, String)).icontains(
                        term, autoescape=True
                    ),
                ),
            }
            for key in ["skill_term", "responsibility_term", "description_term"]:
                hits[key] = and_(visible_job_condition(now), hits[key])
            stmt = stmt.where(or_(*hits.values()))
            rank = rank + sum(case((hit, TEXT_WEIGHTS[key]), else_=0) for key, hit in hits.items())
    for key in ["title", "employer", "location"]:
        if value := getattr(params, key):
            stmt = stmt.where(getattr(Job, key).icontains(value, autoescape=True))
    if params.country:
        # Whole source-supplied restriction labels only; unknown regions are not
        # expanded into invented country membership. [] explicitly means global.
        countries = (
            func.jsonb_array_elements_text(
                case(
                    (
                        func.jsonb_typeof(cast(Job.location_restrictions, JSONB)) == "array",
                        cast(Job.location_restrictions, JSONB),
                    ),
                    else_=cast(literal("[]"), JSONB),
                )
            )
            .table_valued("value")
            .alias("countries")
        )
        stmt = stmt.where(
            or_(
                cast(Job.location_restrictions, JSONB) == cast(literal("[]"), JSONB),
                select(literal(1))
                .select_from(countries)
                .where(func.lower(countries.c.value) == params.country.lower())
                .exists(),
            )
        )
    for key in [
        "employment_type",
        "work_arrangement",
        "source_id",
        "status",
        "salary_currency",
        "salary_period",
    ]:
        if value := getattr(params, key):
            stmt = stmt.where(
                (display_status if key == "status" else getattr(Job, key)) == str(value)
            )
    if params.salary_currency or params.salary_period:
        stmt = stmt.where(visible_job_condition(now))
    for key in ["employment_types", "work_arrangements"]:
        if values := getattr(params, key):
            stmt = stmt.where(
                getattr(Job, key[:-1] if key == "employment_types" else "work_arrangement").in_(
                    values
                )
            )
    if params.skills:
        stmt = stmt.where(visible_job_condition(now))
        stmt = stmt.where(
            or_(*(skill_text_exists(analysis.c.analysis, value.lower()) for value in params.skills))
        )
    for field, value in [
        ("published_at", params.published_after),
        ("source_updated_at", params.updated_after),
        ("last_verified_at", params.verified_after),
    ]:
        if value:
            stmt = stmt.where(getattr(Job, field) >= value)
    for lo, hi, lower, upper in [
        (params.salary_min, params.salary_max, Job.salary_min, Job.salary_max),
        (params.experience_min, params.experience_max, Job.experience_min, Job.experience_max),
    ]:
        if lo is not None:
            stmt = stmt.where(visible_job_condition(now), func.coalesce(upper, lower) >= lo)
        if hi is not None:
            stmt = stmt.where(visible_job_condition(now), func.coalesce(lower, upper) <= hi)
    if params.minimum_score is not None:
        stmt = stmt.where(match.c.is_current, match.c.score >= params.minimum_score)
    if params.eligibility:
        stmt = stmt.where(match.c.is_current, match.c.eligibility_status == params.eligibility)
    if params.required_coverage is not None:
        stmt = stmt.where(match.c.is_current, match.c.required_coverage >= params.required_coverage)
    states = {
        "current": match.c.is_current,
        "stale": and_(match.c.match_id.is_not(None), ~match.c.is_current),
        "missing": match.c.match_id.is_(None),
        "insufficient": and_(match.c.is_current, match.c.score.is_(None)),
    }
    if params.match_state != "any":
        stmt = stmt.where(states[params.match_state])
    score = case((match.c.is_current, match.c.score), else_=None)
    ordering = {
        "recent": [Job.first_seen_at.desc()],
        "text_relevance": [rank.desc()],
        "candidate_match": [score.desc().nullslast()],
        "published_desc": [Job.published_at.desc().nullslast()],
        "verified_desc": [Job.last_verified_at.desc().nullslast()],
        "title": [func.lower(Job.title).collate("C")],
        "employer": [func.lower(Job.employer).collate("C")],
        "salary_desc": [Job.salary_min.desc().nullslast()],
    }
    return stmt.add_columns(
        rank.label("text_rank"),
        match.c.match_id,
        match.c.score,
        match.c.is_current,
        match.c.eligibility_status,
        match.c.assessment_status,
        match.c.ranking_version,
        match.c.required_coverage,
    ).order_by(*ordering[params.sort], Job.id)
