import hashlib
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, text

from app.core.config import settings
from app.core.security import utcnow
from app.db.models import Resume, ResumeExtraction, ResumeProposal, ResumeVersion
from app.db.repositories import current_profile
from app.ingestion.control import lock_key
from app.modules.resumes import validation
from app.modules.resumes.extraction import EXTRACTOR_VERSION, parse_document
from app.modules.resumes.qualification_extraction import extract
from app.modules.resumes.schemas import (
    ExtractionOut,
    ProposalOut,
    ProposalValue,
    ResumeOut,
    VersionOut,
)
from app.modules.resumes.storage import PrivateStorage
from app.modules.resumes.validation import MESSAGES, ResumeError


def fail(exc):
    code = exc.code
    raise HTTPException(
        429
        if code == "parser_busy"
        else 503
        if code in {"storage_unavailable", "isolation_unavailable"}
        else 422,
        MESSAGES.get(code, MESSAGES["parser_failed"]),
    )


def owned_resume(db, user_id, resume_id, lock=False, allow_pending=False):
    profile = current_profile(db, user_id)
    stmt = select(Resume).where(Resume.id == resume_id, Resume.profile_id == profile.id)
    if lock:
        stmt = stmt.with_for_update()
    item = db.scalar(stmt)
    if item is None:
        raise HTTPException(404, "Resume not found")
    if item.status == "deletion_pending" and not allow_pending:
        raise HTTPException(409, "Resume deletion is pending. Retry deletion first")
    return item


def version_for(db, user_id, resume_id, version_id):
    owned_resume(db, user_id, resume_id)
    version = db.scalar(
        select(ResumeVersion).where(
            ResumeVersion.id == version_id, ResumeVersion.resume_id == resume_id
        )
    )
    if not version:
        raise HTTPException(404, "Resume version not found")
    return version


def owned_extraction(db, user_id, extraction_id, lock=False):
    profile = current_profile(db, user_id)
    if lock:
        resume_id = db.scalar(
            select(ResumeVersion.resume_id)
            .join(ResumeExtraction, ResumeExtraction.version_id == ResumeVersion.id)
            .join(Resume, Resume.id == ResumeVersion.resume_id)
            .where(ResumeExtraction.id == extraction_id, Resume.profile_id == profile.id)
        )
        if not resume_id:
            raise HTTPException(404, "Extraction not found")
        service_resume = owned_resume(db, user_id, resume_id, lock=True)
        db.refresh(service_resume)
        if service_resume.status == "deletion_pending":
            raise HTTPException(404, "Extraction not found")
    stmt = (
        select(ResumeExtraction)
        .join(ResumeVersion, ResumeExtraction.version_id == ResumeVersion.id)
        .join(Resume, ResumeVersion.resume_id == Resume.id)
        .where(
            ResumeExtraction.id == extraction_id,
            Resume.profile_id == profile.id,
            Resume.status != "deletion_pending",
        )
    )
    if lock:
        stmt = stmt.with_for_update(of=ResumeExtraction)
    run = db.scalar(stmt)
    if run is None:
        raise HTTPException(404, "Extraction not found")
    return run


def present_resume(db, item):
    versions = db.scalars(
        select(ResumeVersion)
        .where(ResumeVersion.resume_id == item.id)
        .order_by(ResumeVersion.number.desc())
        .limit(20)
    ).all()
    runs = db.scalars(
        select(ResumeExtraction)
        .join(ResumeVersion)
        .where(ResumeVersion.resume_id == item.id)
        .order_by(ResumeVersion.number.desc(), ResumeExtraction.started_at.desc())
        .limit(20)
    ).all()
    return ResumeOut(
        id=item.id,
        name=item.name,
        status=item.status,
        version_count=item.version_count,
        created_at=item.created_at,
        updated_at=item.updated_at,
        versions=[
            VersionOut.model_validate(v).model_copy(
                update={
                    "extraction_id": next((r.id for r in runs if r.version_id == v.id), None),
                    "extraction_status": next(
                        (r.status for r in runs if r.version_id == v.id), None
                    ),
                }
            )
            for v in versions
        ],
        latest_extraction_id=runs[0].id if runs else None,
        latest_successful_extraction_id=next(
            (r.id for r in runs if r.status in {"review_required", "completed"}), None
        ),
    )


def library(db, user_id):
    profile = current_profile(db, user_id)
    items = db.scalars(
        select(Resume)
        .where(Resume.profile_id == profile.id)
        .order_by(Resume.created_at.desc(), Resume.id)
        .limit(10)
    ).all()
    return [present_resume(db, item) for item in items]


def upload(db, user_id, filename, mime, content, resume_id=None):
    profile = current_profile(db, user_id)
    if not content or len(content) > settings.resume_max_bytes:
        raise HTTPException(413, "Resume is empty or exceeds the configured upload size")
    try:
        kind = validation.file_type(filename, mime, content)
        parse_document(content, kind, validate_only=True)
        scan_status = validation.scanner.scan(content, kind)
        if scan_status not in {"not_configured", "scanned_clean"}:
            raise ResumeError("active_document")
    except ResumeError as exc:
        fail(exc)
    # Serialize quota/version counters without locking profile edits for parsing.
    db.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key("resume-upload:" + profile.id)}
    )
    size = db.scalar(
        select(func.coalesce(func.sum(ResumeVersion.size_bytes), 0))
        .join(Resume)
        .where(Resume.profile_id == profile.id)
    )
    if size + len(content) > settings.resume_quota_bytes:
        raise HTTPException(
            409, "Private resume storage quota reached. Delete unused resumes first"
        )
    if resume_id:
        item = owned_resume(db, user_id, resume_id, lock=True)
        if item.version_count >= 20:
            raise HTTPException(409, "At most 20 versions per resume are supported")
    else:
        if (
            db.scalar(
                select(func.count()).select_from(Resume).where(Resume.profile_id == profile.id)
            )
            >= 10
        ):
            raise HTTPException(409, "At most 10 resumes per candidate are supported")
        item = Resume(profile_id=profile.id, name=filename, version_count=0)
        db.add(item)
        db.flush()
    version_id = str(uuid4())
    ref = f"{profile.id}/{version_id}.blob"
    try:
        storage = PrivateStorage()
        storage.write(ref, content)
    except (OSError, ValueError):
        fail(ResumeError("storage_unavailable"))
    db.info.setdefault("resume_rollback_cleanup", []).append(lambda: storage.delete(ref))
    item.version_count += 1
    item.status = "uploaded"
    item.updated_at = utcnow()
    db.add(
        ResumeVersion(
            id=version_id,
            resume_id=item.id,
            number=item.version_count,
            filename=filename,
            storage_ref=ref,
            detected_type=kind,
            size_bytes=len(content),
            checksum=hashlib.sha256(content).hexdigest(),
            scan_status=scan_status,
        )
    )
    db.flush()
    return present_resume(db, item)


def present_extraction(db, run):
    segments = {item["id"]: item for item in run.segments}
    proposals = []
    for proposal in db.scalars(
        select(ResumeProposal)
        .where(ResumeProposal.extraction_id == run.id)
        .order_by(ResumeProposal.category, ResumeProposal.id)
        .limit(100)
    ):
        ev = proposal.evidence
        segment = segments[ev["segment_id"]]
        evidence = {
            **ev,
            "excerpt": segment["text"][ev["start"] : ev["end"]],
            "page": segment["page"],
            "part": segment["part"],
            "version_id": run.version_id,
            "method": run.extractor_version,
        }
        data = {
            key: getattr(proposal, key)
            for key in [
                "id",
                "category",
                "original_value",
                "reviewed_value",
                "review_state",
                "warnings",
                "applied_at",
                "applied_target",
            ]
        }
        proposals.append(ProposalOut(**data, evidence=evidence))
    return ExtractionOut(
        id=run.id,
        version_id=run.version_id,
        extractor_version=run.extractor_version,
        status=run.status,
        revision=run.revision,
        attempts=run.attempts,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error_code=run.error_code,
        error_message=MESSAGES.get(run.error_code) if run.error_code else None,
        quality=run.quality,
        proposals=proposals,
    )


def process(db, user_id, resume_id, version_id):
    item = owned_resume(db, user_id, resume_id, lock=True)
    version = version_for(db, user_id, resume_id, version_id)
    if not db.scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"),
        {"key": lock_key("resume-process:" + version.id)},
    ):
        raise HTTPException(409, "This version is already being processed")
    run = db.scalar(
        select(ResumeExtraction)
        .where(
            ResumeExtraction.version_id == version.id,
            ResumeExtraction.extractor_version == EXTRACTOR_VERSION,
        )
        .with_for_update()
    )
    if run and run.status in {"review_required", "completed"}:
        return present_extraction(db, run)
    if run is None:
        run = ResumeExtraction(
            version_id=version.id, extractor_version=EXTRACTOR_VERSION, attempts=0, revision=0
        )
        db.add(run)
    run.status, run.error_code, run.started_at = "processing", None, utcnow()
    run.attempts += 1
    db.flush()
    try:
        content = PrivateStorage().read(version.storage_ref)
        if hashlib.sha256(content).hexdigest() != version.checksum:
            raise ResumeError("invalid_document")
        parsed = parse_document(content, version.detected_type)
        proposed = extract(parsed["segments"])
        # Validate bounded result shapes before storing any proposals.
        for data in proposed:
            ProposalValue.model_validate(data["original_value"])
        run.segments = parsed["segments"]
        run.quality = {
            **parsed["quality"],
            "proposal_count": len(proposed),
            "qualification_quality": "deterministic suggestions; candidate review required; no numerical confidence",
            "warnings": [
                "Complex layouts and unrecognized fields may be omitted. No external AI or OCR was used."
            ],
        }
        for data in proposed:
            db.add(ResumeProposal(extraction_id=run.id, **data))
        run.status = "review_required"
    except ResumeError as exc:
        run.status, run.error_code = "failed", exc.code
    except (OSError, ValueError):
        run.status, run.error_code = "failed", "parser_failed"
    run.finished_at = utcnow()
    if version.number == item.version_count:
        item.status = run.status
    db.flush()
    return present_extraction(db, run)


def delete(db, user_id, resume_id):
    item = owned_resume(db, user_id, resume_id, lock=True, allow_pending=True)
    # Persist an explicit tombstone before removing bytes. A retry can complete
    # deletion if either the filesystem or final DB commit fails.
    item.status = "deletion_pending"
    db.commit()
    refs = db.scalars(
        select(ResumeVersion.storage_ref).where(ResumeVersion.resume_id == item.id)
    ).all()
    try:
        storage = PrivateStorage()
        for ref in refs:
            storage.delete(ref)
    except (OSError, ValueError):
        return {"status": "deletion_pending"}
    db.delete(item)
    db.flush()
    return {"status": "deleted"}
