from fastapi import HTTPException
from sqlalchemy import select

from app.api.schemas import EducationIn, ExperienceIn, ProfileEdit, ProfileOut, SkillIn
from app.core.security import utcnow
from app.db.models import Resume, ResumeConfirmation, ResumeProposal, ResumeVersion
from app.modules.matching.representations import candidate_snapshot, fingerprint
from app.modules.matching.skills import normalize_skill
from app.modules.resumes import service
from app.services import candidates

ACCEPTED = {"accepted", "edited_accepted"}


def proposals(db, run):
    return list(
        db.scalars(
            select(ResumeProposal)
            .where(ResumeProposal.extraction_id == run.id)
            .order_by(ResumeProposal.id)
        )
    )


def require_reviewable(run):
    if run.status not in {"review_required", "completed"}:
        raise HTTPException(409, "This extraction has no reviewable result")


def review(db, user_id, extraction_id, data):
    run = service.owned_extraction(db, user_id, extraction_id, lock=True)
    require_reviewable(run)
    if run.revision != data.expected_revision:
        raise HTTPException(409, "Review changed. Reload before editing")
    items = {item.id: item for item in proposals(db, run)}
    for decision in data.items:
        item = items.get(str(decision.id))
        if item is None:
            raise HTTPException(404, "Proposal not found in this extraction")
        if item.applied_at:
            raise HTTPException(409, "Applied proposals are immutable; edit the profile directly")
        item.review_state = decision.decision
        item.reviewed_value = (
            decision.value.model_dump(mode="json", exclude_unset=True) if decision.value else None
        )
        item.reviewed_at = utcnow()
    run.revision += 1
    update_status(db, run)
    db.flush()
    return service.present_extraction(db, run)


def profile_fingerprint(profile):
    return fingerprint(
        ProfileOut.model_validate(profile).model_dump(mode="json", exclude={"updated_at"})
    )


def value_of(item):
    return item.reviewed_value if item.review_state == "edited_accepted" else item.original_value


def plan(profile, item):
    value = value_of(item)
    if item.applied_at:
        return {
            "id": item.id,
            "category": item.category,
            "action": "already_applied",
            "target": item.applied_target,
        }
    if item.review_state not in ACCEPTED:
        return {"id": item.id, "category": item.category, "action": "not_accepted"}
    category = item.category
    result = {"id": item.id, "category": category, "action": "add", "value": value}
    if category == "skill":
        validated = SkillIn(name=value.get("name"))
        existing = next(
            (
                s
                for s in profile.skills
                if normalize_skill(s.name) == normalize_skill(validated.name)
            ),
            None,
        )
        result.update(
            value=validated.model_dump(),
            action="duplicate" if existing else "add",
            target={"kind": "skill", "id": existing.id} if existing else None,
        )
    elif category in {"experience", "education"}:
        model = ExperienceIn if category == "experience" else EducationIn
        fields = model.model_fields.keys()
        validated = model.model_validate({key: val for key, val in value.items() if key in fields})
        payload = validated.model_dump(mode="json")
        items = profile.experience if category == "experience" else profile.education
        keys = (
            ["employer", "title"] if category == "experience" else ["institution", "qualification"]
        )
        similar = [
            old
            for old in items
            if all(
                str(getattr(old, key)).casefold() == str(payload[key]).casefold() for key in keys
            )
        ]
        exact = next(
            (
                old
                for old in similar
                if model.model_validate(old).model_dump(mode="json") == payload
            ),
            None,
        )
        result.update(
            value=payload,
            action="duplicate" if exact else "conflict" if similar else "add",
            target={"kind": category, "id": exact.id} if exact else None,
        )
        if similar and not exact:
            result["existing"] = [
                {"id": old.id, **model.model_validate(old).model_dump(mode="json")}
                for old in similar
            ]
            result["allowed_resolutions"] = ["skip", "add_separate"]
    elif category == "summary":
        validated = ProfileEdit(summary=value.get("text"))
        if not validated.summary:
            raise HTTPException(422, "A summary needs nonempty reviewed text")
        result["value"] = {"text": validated.summary}
        result["action"] = (
            "duplicate"
            if profile.summary == validated.summary
            else "conflict"
            if profile.summary
            else "add"
        )
        result["existing"] = profile.summary
        result["allowed_resolutions"] = ["skip", "replace_summary"]
    else:
        text = value.get("profile_text")
        if not text:
            raise HTTPException(422, "Review and supply the exact profile text before confirmation")
        if category == "certification":
            text += " | validity not verified"
        field = {
            "certification": "certifications",
            "project": "projects",
            "language": "qualifications",
        }[category]
        ProfileEdit.model_validate({field: [text]})
        result.update(
            value={"field": field, "text": text},
            action="duplicate"
            if any(old.casefold() == text.casefold() for old in getattr(profile, field))
            else "add",
        )
    return result


def preview(db, user_id, extraction_id):
    run = service.owned_extraction(db, user_id, extraction_id)
    require_reviewable(run)
    profile = candidates.locked_profile(db, user_id)
    items = proposals(db, run)
    plans = []
    for item in items:
        try:
            plans.append(plan(profile, item))
        except ValueError:
            plans.append(
                {
                    "id": item.id,
                    "category": item.category,
                    "action": "invalid_fields",
                    "message": "Correct required fields, lengths and dates before confirming",
                }
            )
        except HTTPException as exc:
            plans.append(
                {
                    "id": item.id,
                    "category": item.category,
                    "action": "invalid_fields",
                    "message": str(exc.detail),
                }
            )
    return {
        "extraction_id": run.id,
        "revision": run.revision,
        "profile_fingerprint": profile_fingerprint(profile),
        "items": plans,
        "unresolved_count": sum(
            not item.applied_at and item.review_state != "rejected" for item in items
        ),
    }


def update_status(db, run):
    remaining = any(
        not item.applied_at and item.review_state != "rejected" for item in proposals(db, run)
    )
    run.status = "review_required" if remaining else "completed"
    version = db.get(ResumeVersion, run.version_id)
    resume = db.get(Resume, version.resume_id)
    if version.number == resume.version_count and resume.status != "deletion_pending":
        resume.status = run.status


def confirm(db, user_id, extraction_id, data):
    run = service.owned_extraction(db, user_id, extraction_id, lock=True)
    require_reviewable(run)
    request_fp = fingerprint(data.model_dump(mode="json"))
    prior = db.scalar(
        select(ResumeConfirmation).where(
            ResumeConfirmation.extraction_id == run.id,
            ResumeConfirmation.request_key == str(data.request_key),
        )
    )
    if prior:
        if prior.request_fingerprint != request_fp:
            raise HTTPException(409, "Confirmation key already used with different choices")
        return prior.result
    profile = candidates.locked_profile(db, user_id)
    if (
        run.revision != data.expected_revision
        or profile_fingerprint(profile) != data.expected_profile_fingerprint
    ):
        raise HTTPException(409, "Review or profile changed. Preview again before confirming")
    items = {item.id: item for item in proposals(db, run)}
    selected = [items.get(str(key)) for key in data.item_ids]
    if any(item is None for item in selected):
        raise HTTPException(404, "Proposal not found in this extraction")
    if sum(item.category == "summary" and not item.applied_at for item in selected) > 1:
        raise HTTPException(
            409,
            "Confirm one summary proposal at a time; combine reviewed text explicitly if needed",
        )
    before = fingerprint(candidate_snapshot(profile))
    changes = []
    for item in selected:
        entry = plan(profile, item)
        action = entry["action"]
        if action == "not_accepted":
            raise HTTPException(409, "Only explicitly accepted items can be confirmed")
        resolution = data.resolutions.get(item.id)
        if action == "conflict" and resolution not in entry["allowed_resolutions"]:
            raise HTTPException(409, "Resolve the displayed profile conflict explicitly")
        if resolution and action != "conflict" and resolution != "skip":
            raise HTTPException(422, "This resolution is not applicable to the proposal")
        target = entry.get("target") or {"kind": item.category}
        if action == "already_applied":
            changes.append({"proposal_id": item.id, "action": action, "target": target})
            continue
        if resolution == "skip":
            action = "skipped_existing_preserved"
        elif action != "duplicate":
            value = entry["value"]
            if item.category == "skill":
                saved = candidates.add_skill(db, user_id, SkillIn(**value))
                target["id"] = saved.id
            elif item.category in {"experience", "education"}:
                kind = item.category
                model = ExperienceIn if kind == "experience" else EducationIn
                saved = candidates.save_child(db, user_id, kind, model.model_validate(value))
                target["id"] = saved.id
            elif item.category == "summary":
                candidates.update_profile(db, user_id, ProfileEdit(summary=value["text"]))
                target["field"] = "summary"
            else:
                field = value["field"]
                candidates.update_profile(
                    db,
                    user_id,
                    ProfileEdit.model_validate({field: [*getattr(profile, field), value["text"]]}),
                )
                target["field"] = field
            action = (
                "added_separately"
                if resolution == "add_separate"
                else "replaced_summary_explicitly"
                if resolution == "replace_summary"
                else "added"
            )
        item.applied_at, item.applied_target = utcnow(), target
        changes.append({"proposal_id": item.id, "action": action, "target": target})
        db.flush()
        db.refresh(profile)
    run.revision += 1
    update_status(db, run)
    db.refresh(profile)
    result = {
        "confirmation_id": str(__import__("uuid").uuid4()),
        "changes": changes,
        "unresolved_count": sum(
            not item.applied_at and item.review_state != "rejected" for item in items.values()
        ),
        "matching_requires_refresh": before != fingerprint(candidate_snapshot(profile)),
        "status": run.status,
    }
    db.add(
        ResumeConfirmation(
            id=result["confirmation_id"],
            extraction_id=run.id,
            request_key=str(data.request_key),
            request_fingerprint=request_fp,
            result=result,
        )
    )
    candidates.audit(db, user_id, "resume.confirmed", run.id)
    db.flush()
    return result
