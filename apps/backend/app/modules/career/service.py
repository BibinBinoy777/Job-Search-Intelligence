from fastapi import HTTPException
from sqlalchemy import func, or_, select

from app.core.security import utcnow
from app.db.models import Job, JobRequirementAnalysis, JobSource
from app.ingestion.freshness import visible_job_condition
from app.modules.career.analysis import (
    VERSION,
    deduplicate,
    gaps_from,
    public_listing,
    recommend_roles,
    requirements,
    role_key,
    role_matches,
    sample_breakdown,
    statistics,
)
from app.modules.career.evidence import candidate_evidence
from app.modules.career.resources import learning_for
from app.modules.career.schemas import CareerOut
from app.modules.matching.candidate import analyze_candidate
from app.modules.matching.config import CONFIG
from app.modules.matching.representations import candidate_snapshot, fingerprint, job_snapshot
from app.modules.matching.requirements import analyze_requirements
from app.services.candidates import locked_profile

MAX_LISTINGS = 500


def retrieve(db, filters, now):
    conditions = []
    if filters.source_id:
        if not db.get(JobSource, str(filters.source_id)):
            raise HTTPException(404, "Job source not found")
        conditions.append(Job.source_id == str(filters.source_id))
    if filters.location:
        # Same literal substring semantics as existing discovery; no country inference.
        conditions.append(Job.location.icontains(filters.location, autoescape=True))
    if filters.published_after:
        conditions.append(Job.published_at >= filters.published_after)
    if filters.published_before:
        conditions.append(Job.published_at < filters.published_before)
    base_count = db.scalar(select(func.count()).select_from(Job).where(*conditions))
    availability = [
        visible_job_condition(now),
        Job.status.not_in(["closed", "expired"]),
        or_(Job.source_expires_at.is_(None), Job.source_expires_at > now),
    ]
    count = db.scalar(select(func.count()).select_from(Job).where(*conditions, *availability))
    jobs = (
        db.scalars(
            select(Job)
            .where(*conditions, *availability)
            .order_by(Job.last_verified_at.desc().nullslast(), Job.id)
            .limit(MAX_LISTINGS)
        )
        .unique()
        .all()
    )
    snapshots = {job.id: job_snapshot(job) for job in jobs}
    fps = {job_id: fingerprint(snapshot) for job_id, snapshot in snapshots.items()}
    cache = {}
    if jobs:
        rows = db.scalars(
            select(JobRequirementAnalysis).where(
                JobRequirementAnalysis.job_id.in_(list(snapshots)),
                JobRequirementAnalysis.content_fingerprint.in_(list(fps.values())),
                JobRequirementAnalysis.extractor_version == CONFIG.extractor_version,
            )
        ).all()
        cache = {(r.job_id, r.content_fingerprint): r.analysis for r in rows}
    records = [
        {
            "job": job,
            "snapshot": snapshots[job.id],
            "analysis": cache.get((job.id, fps[job.id])) or analyze_requirements(snapshots[job.id]),
        }
        for job in jobs
    ]
    return records, count, base_count - count


def transitions_for(snapshot, records, roles, selected_origin, evidence):
    experience = snapshot["experience"]
    original_titles = list(dict.fromkeys(e["title"] for e in experience))
    titles = list(dict.fromkeys(original_titles + [r["job"].title for r in records]))
    origin = selected_origin or (original_titles[0] if original_titles else None)
    if selected_origin and selected_origin not in titles:
        raise HTTPException(
            422, "Choose an origin from recorded experience or the scoped listing titles"
        )
    if not origin:
        return titles, []
    own = [e for e in experience if e["title"] == origin]
    origin_records = [r for r in records if role_key(r["job"].title) == role_key(origin)]
    known = {s["name"] for s in evidence if s["used_for_role_overlap"]}
    if own:
        origin_candidate = analyze_candidate({"experience": own})
        origin_names = {entries[0]["name"] for entries in origin_candidate["skills"].values()}
        references = [{"kind": "profile_record", "path": f"experience/{e['id']}"} for e in own]
    else:
        origin_names = {
            skill["name"] for r in origin_records for _, skill in requirements(r)
        } & known
        references = [
            {"kind": "listing_requirement", "job_id": r["job"].id} for r in origin_records
        ]
    result = []
    for role in roles:
        if role_key(origin) == role_key(role["title"]):
            continue
        transferable = sorted(origin_names & set(role["overlap"]))
        if not transferable:
            continue
        supports = {
            listing["id"]: listing
            for listing in [
                *[public_listing(r["job"]) for r in origin_records[:10]],
                *role["representative_listings"],
            ]
        }
        result.append(
            {
                "origin": origin,
                "origin_kind": "recorded_experience" if own else "selected_exploration",
                "origin_evidence": references,
                "destination_id": role["id"],
                "destination": role["title"],
                "transferable_skills": transferable,
                "skills_to_investigate": role["missing_skills"],
                "additional_requirements": role["additional_requirements"],
                "supporting_listings": list(supports.values()),
                "next_steps": [
                    "Compare the cited role-specific requirements with your actual work.",
                    "Review missing skill evidence, qualification alternatives and any licensing/work authorization conditions.",
                    "Choose a relevant practice task or investigate a better-supported intermediate role; no standard route is established.",
                ],
                "evidence_strength": "inferred pathway from recorded evidence",
                "limitations": [
                    "Shared requirements suggest a route to investigate, not an established progression.",
                    "No transition duration, salary gain, promotion probability or hiring eligibility is established.",
                    "No intermediate step is asserted without supporting role evidence.",
                ],
            }
        )
    return titles, result


def overview(db, user_id, filters):
    now = utcnow()
    # Share the existing profile mutation lock to keep one dashboard input stable.
    profile = locked_profile(db, user_id)
    snapshot = candidate_snapshot(profile)
    candidate, evidence = candidate_evidence(db, profile, snapshot)
    records, scoped_count, excluded = retrieve(db, filters, now)
    unique, duplicates = deduplicate(records)
    targets = (
        [filters.target_role]
        if filters.target_role
        else (snapshot.get("preferences") or {}).get("target_titles", [])
    )
    known = {s["key"] for s in evidence if s["used_for_role_overlap"]}
    if targets:
        relevant = [
            r for r in unique if any(role_matches(r["job"].title, target) for target in targets)
        ]
        basis = "All normalized target-role tokens must be present in a collected listing title; existing title aliases are reused."
    else:
        relevant = [r for r in unique if known & {s["key"] for _, s in requirements(r)}]
        basis = "No target role selected: at least one recorded profile skill overlaps an explicit required/preferred listing skill. Unconfirmed resume suggestions are excluded."
    stats = statistics(relevant, evidence, filters.requirement_kind)
    gaps = gaps_from(stats, evidence)
    roles = recommend_roles(unique, evidence)
    origins, transitions = transitions_for(snapshot, unique, roles, filters.origin_role, evidence)
    usable = sum(bool(requirements(r)) for r in relevant)
    limitations = [
        "These statistics describe collected eligible listings in this dataset, not the broader labor market or statistical significance.",
        "Eligible means passing data-scope/availability filters, not candidate hiring eligibility. Manual/legacy listings may have unverified availability.",
        "Exact employer/title/location/content duplicates are counted once. Identical separate vacancies may be merged; undetected near-duplicates can remain.",
        "Unknown publication dates are excluded when a publication filter is supplied. No modification date is relabeled publication.",
        "Deterministic requirements omit unrecognized skills, ambiguous alternatives and domain knowledge outside the existing taxonomy. Incidental mentions are excluded.",
        "No time trend or geographic difference is inferred from a single sample; location groups are source-supplied strings, not verified jurisdictions.",
        "Small or sparse samples offer limited evidence; confidence labels are descriptive heuristics, not calibrated statistics.",
    ]
    if scoped_count > MAX_LISTINGS:
        limitations.append(
            f"Partial population: only the first {MAX_LISTINGS} scoped records, ordered by verification time and ID, were analyzed. Narrow source/location/publication filters; denominators refer only to this examined subset."
        )
    if usable < len(relevant):
        limitations.append(
            f"{len(relevant) - usable} relevant listing(s) have no recognized required/preferred skill evidence; they remain in the denominator."
        )
    market = {
        "stored_listing_records": db.scalar(select(func.count()).select_from(Job)),
        "scoped_records": scoped_count,
        "excluded_unavailable": excluded,
        "analyzed_records": len(records),
        "population_truncated": scoped_count > MAX_LISTINGS,
        "duplicate_records_excluded": duplicates,
        "unique_scoped_listings": len(unique),
        "relevant_listings": len(relevant),
        "listings_with_usable_requirements": usable,
        "denominator_definition": "Distinct relevant listings in the examined eligible sample, including listings with no recognized skills. Each skill is counted at most once per listing; required/preferred use the existing extractor's strongest classification.",
        "relevance_basis": basis,
        "target_roles": targets,
        "requirement_kind": filters.requirement_kind,
        **sample_breakdown(relevant),
        "geography_definition": "Literal source-supplied listing location strings. No inferred country, work authorization or nationwide representativeness.",
        "limitations": limitations,
    }
    notices = [
        "Unconfirmed resume proposals never become profile facts here. Review and confirmation stay in Resume intelligence.",
        "Role suggestions use the larger scoped listing population; gap statistics use only the displayed relevant target-role population. They may have different counts.",
        "Analysis is read-only and recomputed for this request. No matching assessment is recalculated or marked current.",
        "Resource verification is a dated identity/content check, not live availability, credential recognition or employment assurance.",
    ]
    learning = learning_for(gaps, now.date())
    return CareerOut(
        analysis_version=VERSION,
        generated_at=now,
        input_fingerprint=fingerprint(
            {
                "candidate": snapshot,
                "evidence": evidence,
                "filters": filters.model_dump(mode="json"),
                "market": market,
                "learning": learning,
                "jobs": [
                    {
                        "id": r["job"].id,
                        "content": r["snapshot"],
                        "verified": r["job"].last_verified_at,
                        "published": r["job"].published_at,
                        "expires": r["job"].source_expires_at,
                        "source_id": r["job"].source_id,
                    }
                    for r in unique
                ],
                "day": now.date().isoformat(),
            }
        ),
        filters=filters,
        profile_completeness=candidate["completeness"],
        candidate_skills=evidence,
        origin_roles=origins,
        market=market,
        skill_statistics=stats,
        gaps=gaps,
        roles=roles,
        transitions=transitions,
        learning=learning,
        notices=notices,
    )
