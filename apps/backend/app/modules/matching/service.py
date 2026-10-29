import copy

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from app.api.schemas import JobOut
from app.core.security import utcnow
from app.db.models import Job, JobRequirementAnalysis, MatchingRefresh, MatchResult
from app.db.repositories import current_profile, job_by_id
from app.ingestion.control import lock_key
from app.ingestion.freshness import visible_job_condition
from app.modules.matching.candidate import analyze_candidate
from app.modules.matching.config import CONFIG
from app.modules.matching.engine import evaluate
from app.modules.matching.representations import (
    candidate_snapshot,
    fingerprint,
    job_input_fingerprint,
    job_snapshot,
)
from app.modules.matching.requirements import analyze_requirements
from app.modules.matching.schemas import Assessment, MatchOut, PairOut


def consideration_condition():
    return visible_job_condition() & Job.status.not_in(["closed", "expired"])


def load_context(db, user_id):
    profile = current_profile(db, user_id)
    snapshot = candidate_snapshot(profile)
    return profile, snapshot, fingerprint(snapshot)


def analyze_job(db, job, cache, snapshot):
    content = fingerprint(snapshot)
    key = (job.id, content)
    if key in cache:
        return cache[key]
    analysis = analyze_requirements(snapshot)
    db.execute(
        insert(JobRequirementAnalysis)
        .values(
            job_id=job.id,
            content_fingerprint=content,
            extractor_version=CONFIG.extractor_version,
            job_snapshot=snapshot,
            analysis=analysis,
        )
        .on_conflict_do_nothing(constraint="uq_requirement_analysis")
    )
    record = db.scalar(
        select(JobRequirementAnalysis).where(
            JobRequirementAnalysis.job_id == job.id,
            JobRequirementAnalysis.content_fingerprint == content,
            JobRequirementAnalysis.extractor_version == CONFIG.extractor_version,
        )
    )
    cache[key] = record
    return record


def refresh(db, user_id, data):
    profile, snapshot, candidate_fp = load_context(db, user_id)
    # Transaction advisory lock is released on commit/rollback, serializing this
    # candidate's refreshes while leaving ingestion and other candidates usable.
    if not db.scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": lock_key("matching:" + profile.id)}
    ):
        raise HTTPException(409, "Your recommendation refresh is already running")
    # Fingerprint again on reads: any concurrent child edit makes this snapshot
    # stale without claiming that a completed refresh assessed the later edit.
    started = utcnow()
    stmt = select(Job).where(consideration_condition())
    if data.job_ids:
        requested = {str(v) for v in data.job_ids}
        existing = set(db.scalars(select(Job.id).where(Job.id.in_(requested))))
        if existing != requested:
            raise HTTPException(404, "One or more jobs do not exist")
        stmt = stmt.where(Job.id.in_(requested))
    if data.after_job_id:
        stmt = stmt.where(Job.id > str(data.after_job_id))
    jobs = list(db.scalars(stmt.order_by(Job.id).limit(data.limit + 1)).unique())
    more = len(jobs) > data.limit
    jobs = jobs[: data.limit]
    ids = [j.id for j in jobs]
    cached = (
        db.scalars(
            select(JobRequirementAnalysis).where(
                JobRequirementAnalysis.job_id.in_(ids),
                JobRequirementAnalysis.extractor_version == CONFIG.extractor_version,
            )
        ).all()
        if ids
        else []
    )
    cache = {(r.job_id, r.content_fingerprint): r for r in cached}
    existing_results = (
        db.scalars(
            select(MatchResult).where(
                MatchResult.profile_id == profile.id,
                MatchResult.job_id.in_(ids),
                MatchResult.candidate_fingerprint == candidate_fp,
                MatchResult.ranking_version == CONFIG.identity,
                MatchResult.config_fingerprint == CONFIG.fingerprint,
            )
        ).all()
        if ids
        else []
    )
    matches = {(r.job_id, r.job_fingerprint): r for r in existing_results}
    calculated = reused = 0
    errors = []
    for job in jobs:
        content = job_snapshot(job)
        job_fp = job_input_fingerprint(job, content, started.date())
        if (job.id, job_fp) in matches:
            # Only an exact complete input fingerprint may upgrade the optional
            # search context on an older assessment without recomputing its score.
            record = matches[(job.id, job_fp)]
            if record.job_context is None:
                record.job_context = {
                    key: value.isoformat() if hasattr(value, "isoformat") else value
                    for key, value in {
                        "status": job.status,
                        "status_basis": job.status_basis,
                        "last_verified_at": job.last_verified_at,
                        "source_expires_at": job.source_expires_at,
                        "source_id": job.source_id,
                        "external_id": job.external_id,
                    }.items()
                }
                record.assessment_day = started.date()
            reused += 1
            continue
        try:
            with db.begin_nested():
                analysis = analyze_job(db, job, cache, content)
                context = {
                    **content,
                    "status": job.status,
                    "status_basis": job.status_basis,
                    "last_verified_at": job.last_verified_at,
                    "source_expires_at": job.source_expires_at,
                }
                outcome = Assessment.model_validate(
                    evaluate(snapshot, context, analysis.analysis, started, config=CONFIG)
                ).model_dump(mode="json")
                db.execute(
                    insert(MatchResult)
                    .values(
                        profile_id=profile.id,
                        job_id=job.id,
                        analysis_id=analysis.id,
                        candidate_fingerprint=candidate_fp,
                        job_fingerprint=job_fp,
                        ranking_version=CONFIG.identity,
                        config_fingerprint=CONFIG.fingerprint,
                        candidate_snapshot=snapshot,
                        job_context={
                            key: value.isoformat() if hasattr(value, "isoformat") else value
                            for key, value in {
                                "status": job.status,
                                "status_basis": job.status_basis,
                                "last_verified_at": job.last_verified_at,
                                "source_expires_at": job.source_expires_at,
                                "source_id": job.source_id,
                                "external_id": job.external_id,
                            }.items()
                        },
                        assessment_day=started.date(),
                        score=outcome["score"],
                        eligibility_status=outcome["eligibility"]["status"],
                        evidence_coverage=outcome["evidence_coverage"]["value"],
                        assessment_status=outcome["assessment_status"],
                        result=outcome,
                    )
                    .on_conflict_do_nothing(constraint="uq_match_inputs")
                )
            calculated += 1
        except (ValidationError, ValueError):
            cache.pop((job.id, fingerprint(content)), None)
            errors.append({"job_id": job.id, "code": "matching_input_or_output_invalid"})
    run = MatchingRefresh(
        profile_id=profile.id,
        ranking_version=CONFIG.identity,
        candidate_fingerprint=candidate_fp,
        status="partial" if more or errors else "complete",
        considered=len(jobs),
        calculated=calculated,
        reused=reused,
        failed=len(errors),
        has_more=more,
        next_job_id=jobs[-1].id if more and jobs else None,
        errors=errors,
        started_at=started,
        finished_at=utcnow(),
    )
    db.add(run)
    db.flush()
    return run


def staleness(record, candidate_fp, job):
    reasons = []
    if record.candidate_fingerprint != candidate_fp:
        reasons.append("candidate_information_changed")
    if record.job_fingerprint != job_input_fingerprint(job, job_snapshot(job)):
        reasons.append("job_information_availability_or_assessment_date_changed")
    if record.ranking_version != CONFIG.identity or record.config_fingerprint != CONFIG.fingerprint:
        reasons.append("ranking_configuration_changed")
    if (
        job.source
        and job.source.adapter_key
        and (job.last_verified_at is None or not JobOut.model_validate(job).is_available)
    ):
        reasons.append("listing_availability_unverified_or_stale")
    if (
        job.status in {"closed", "expired"}
        or job.source_expires_at
        and job.source_expires_at <= utcnow()
    ):
        reasons.append("listing_unavailable")
    return reasons


def present(record, job, candidate_fp):
    reasons = staleness(record, candidate_fp, job)
    payload = copy.deepcopy(record.result)
    current = JobOut.model_validate(job)
    if not current.is_available or job.status in {"closed", "expired"}:
        for group in ["required", "preferred", "ambiguous_mentions"]:
            for item in payload["skills"][group]:
                item["job_evidence"] = []
                item.pop("evidence", None)
        for check in payload["eligibility"]["checks"]:
            check["evidence"] = {}
        for feature in payload["features"].values():
            feature["details"] = {}
        payload["data_quality"]["warnings"].append(
            "Historical source snippets suppressed because the listing is unavailable."
        )
    return MatchOut(
        id=record.id,
        job=current,
        score=record.score,
        eligibility_status=record.eligibility_status,
        assessment_status=record.assessment_status,
        evidence_coverage=record.evidence_coverage,
        ranking_version=record.ranking_version,
        config_fingerprint=record.config_fingerprint,
        candidate_fingerprint=record.candidate_fingerprint,
        job_fingerprint=record.job_fingerprint,
        generated_at=record.generated_at,
        is_stale=bool(reasons),
        stale_reasons=reasons,
        assessment=Assessment.model_validate(payload),
    )


def latest(db, profile_id, job_ids=None, candidate_fp=None, jobs=None):
    stmt = select(MatchResult).where(MatchResult.profile_id == profile_id)
    if job_ids is not None:
        stmt = stmt.where(MatchResult.job_id.in_(job_ids))
    preferred = {}
    if candidate_fp is not None and jobs:
        fingerprints = {
            key: job_input_fingerprint(value, job_snapshot(value)) for key, value in jobs.items()
        }
        exact = db.scalars(
            stmt.where(
                MatchResult.candidate_fingerprint == candidate_fp,
                MatchResult.ranking_version == CONFIG.identity,
                MatchResult.config_fingerprint == CONFIG.fingerprint,
            ).order_by(MatchResult.generated_at.desc(), MatchResult.id.desc())
        )
        for row in exact:
            if row.job_id not in preferred and row.job_fingerprint == fingerprints.get(row.job_id):
                preferred[row.job_id] = row
    # PostgreSQL DISTINCT ON selects one latest private result per job, retaining
    # old versions in storage without accidental duplicate active list entries.
    fallback = db.scalars(
        stmt.distinct(MatchResult.job_id).order_by(
            MatchResult.job_id, MatchResult.generated_at.desc(), MatchResult.id.desc()
        )
    ).all()
    return [preferred.get(row.job_id, row) for row in fallback]


def pair(db, user_id, job_id):
    profile, _, candidate_fp = load_context(db, user_id)
    job = job_by_id(db, job_id)
    results = latest(db, profile.id, [job.id], candidate_fp, {job.id: job})
    if not results:
        return PairOut(
            state="not_calculated",
            match=None,
            message="No match has been calculated for your current profile and this job. Refresh to assess available jobs.",
        )
    result = present(results[0], job, candidate_fp)
    return PairOut(
        state="stale" if result.is_stale else "current",
        match=result,
        message="This stored assessment needs a refresh."
        if result.is_stale
        else "Assessment based on the recorded professional evidence.",
    )


def recommendations(
    db,
    user_id,
    page,
    page_size,
    minimum_score=None,
    eligibility=None,
    location=None,
    employment_type=None,
    work_arrangement=None,
    source_id=None,
    required_coverage=None,
    include_stale=False,
):
    profile, _, candidate_fp = load_context(db, user_id)
    stmt = select(Job).where(consideration_condition())
    for key, value in [
        ("employment_type", employment_type),
        ("work_arrangement", work_arrangement),
        ("source_id", source_id),
    ]:
        if value:
            stmt = stmt.where(getattr(Job, key) == value)
    if location:
        stmt = stmt.where(Job.location.icontains(location, autoescape=True))
    jobs = {j.id: j for j in db.scalars(stmt).unique()}
    rows = latest(db, profile.id, list(jobs), candidate_fp, jobs) if jobs else []
    results = []
    for row in rows:
        result = present(row, jobs[row.job_id], candidate_fp)
        if result.is_stale and not include_stale:
            continue
        if eligibility:
            if result.eligibility_status != eligibility:
                continue
        elif result.eligibility_status == "confirmed_mismatch":
            continue
        if minimum_score is not None and (result.score is None or result.score < minimum_score):
            continue
        coverage = result.assessment.features["required_skills"].value
        if required_coverage is not None and (coverage is None or coverage < required_coverage):
            continue
        results.append(result)
    results.sort(key=lambda r: (r.is_stale, r.score is None, -(r.score or 0), r.job.id))
    return {
        "items": results[(page - 1) * page_size : page * page_size],
        "total": len(results),
        "page": page,
        "page_size": page_size,
    }


def status(db, user_id):
    profile, snapshot, candidate_fp = load_context(db, user_id)
    jobs = {j.id: j for j in db.scalars(select(Job).where(consideration_condition())).unique()}
    rows = latest(db, profile.id, list(jobs), candidate_fp, jobs) if jobs else []
    current = sum(not staleness(r, candidate_fp, jobs[r.job_id]) for r in rows)
    last = db.scalar(
        select(MatchingRefresh)
        .where(MatchingRefresh.profile_id == profile.id)
        .order_by(MatchingRefresh.finished_at.desc(), MatchingRefresh.id.desc())
        .limit(1)
    )
    return {
        "ranking_version": CONFIG.identity,
        "config": CONFIG.manifest(),
        "candidate_fingerprint": candidate_fp,
        "profile_completeness": analyze_candidate(snapshot)["completeness"],
        "available_job_count": len(jobs),
        "current_results": current,
        "stale_results": len(rows) - current,
        "uncalculated_jobs": len(jobs) - len(rows),
        "all_available_jobs_current": current == len(jobs),
        "last_refresh": last,
        "max_batch": CONFIG.max_batch,
    }
