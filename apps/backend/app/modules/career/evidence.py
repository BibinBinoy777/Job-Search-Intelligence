from sqlalchemy import select

from app.db.models import Resume, ResumeExtraction, ResumeProposal, ResumeVersion
from app.modules.matching.candidate import analyze_candidate
from app.modules.matching.skills import normalize_skill, skill_name


def candidate_evidence(db, profile, snapshot):
    """Return references, never raw resume text, names, contacts or private excerpts."""
    candidate = analyze_candidate(snapshot)
    result = {}
    for key, entries in candidate["skills"].items():
        direct = any(e["path"].startswith("skills/") for e in entries)
        documented = any(e["kind"] == "explicit" for e in entries)
        status = "confirmed" if direct else "resume_evidenced" if documented else "inferred"
        result[key] = {
            "key": key,
            "name": skill_name(key),
            "status": status,
            "used_for_role_overlap": True,
            "sources": [
                {"kind": "profile_record", "path": e["path"], "evidence_kind": e["kind"]}
                for e in entries
            ],
            "note": "Candidate-recorded skill, not independently verified."
            if direct
            else "Documented experience/technology, not independently verified."
            if documented
            else "Skill mention inferred from recorded profile text; inspect the profile before relying on it.",
        }
    proposals = db.scalars(
        select(ResumeProposal)
        .join(ResumeExtraction)
        .join(ResumeVersion)
        .join(Resume)
        .where(
            Resume.profile_id == profile.id,
            Resume.status != "deletion_pending",
            ResumeExtraction.status.in_(["review_required", "completed"]),
            ResumeProposal.category == "skill",
            ResumeProposal.review_state.in_(
                ["pending", "accepted", "edited_accepted", "needs_clarification"]
            ),
        )
        .order_by(ResumeProposal.id)
    ).all()
    for proposal in proposals:
        # A candidate correction is a suggestion until it is explicitly applied.
        value = (
            proposal.reviewed_value
            if proposal.review_state == "edited_accepted"
            else proposal.original_value
        )
        if not value or not value.get("name"):
            continue
        key = normalize_skill(value["name"])
        if proposal.applied_at:
            target = proposal.applied_target or {}
            current_ids = {s["id"] for s in snapshot["skills"] if normalize_skill(s["name"]) == key}
            if key in result and target.get("kind") == "skill" and target.get("id") in current_ids:
                result[key]["sources"].append(
                    {
                        "kind": "confirmed_resume_record",
                        "proposal_id": proposal.id,
                        "extraction_id": proposal.extraction_id,
                        "review_state": proposal.review_state,
                    }
                )
            continue
        source = {
            "kind": "unconfirmed_resume_proposal",
            "proposal_id": proposal.id,
            "extraction_id": proposal.extraction_id,
            "review_state": proposal.review_state,
        }
        if key in result:
            result[key]["sources"].append(source)
        else:
            result[key] = {
                "key": key,
                "name": skill_name(key),
                "status": "resume_evidenced",
                "used_for_role_overlap": False,
                "sources": [source],
                "note": "Unconfirmed resume suggestion. Review and explicitly confirm it; it does not establish a profile qualification or role fit.",
            }
    return candidate, sorted(
        result.values(), key=lambda r: (r["status"] != "confirmed", r["name"].casefold())
    )
