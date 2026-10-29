import hashlib
import re

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.api.schemas import JobIn
from app.core.security import utcnow
from app.db.models import DuplicateCandidate, Job
from app.ingestion.freshness import listing_state

METADATA_FIELDS = {
    "source_updated_at",
    "source_expires_at",
    "location_restrictions",
    "timezone_restrictions",
    "source_categories",
}


def description_digest(text):
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().casefold().encode()).hexdigest()


def persist_observation(db, normalized, verification, run_id=None):
    data = normalized.data
    patch = data.model_dump(exclude_unset=True, exclude={"skills", "status", "last_verified_at"})
    patch = {key: value for key, value in patch.items() if value is not None}
    patch["source_url"] = str(patch["source_url"])
    metadata = {
        key: value
        for key, value in normalized.metadata.items()
        if key in METADATA_FIELDS and value is not None
    }
    now = utcnow()
    initial = {
        **patch,
        **metadata,
        "status": "unknown",
        "description_fingerprint": description_digest(data.description),
    }
    inserted = db.scalar(
        insert(Job)
        .values(**initial)
        .on_conflict_do_nothing(constraint="uq_job_source_identity")
        .returning(Job.id)
    )
    item = db.scalar(
        select(Job)
        .where(Job.source_id == data.source_id, Job.external_id == data.external_id)
        .with_for_update(of=Job)
    )
    from app.modules.automation.events import capture, content_version

    old_content, old_status = content_version(item), item.status
    # Revalidate merged partial updates; omissions and NULL do not erase known data.
    previous = JobIn.model_validate(item).model_dump(exclude={"skills"})
    if ("salary_min" in patch or "salary_max" in patch) and any(
        patch.get(key) != previous[key] for key in ["salary_currency", "salary_period"]
    ):
        # Never reinterpret a retained annual/USD bound as a monthly/INR amount.
        patch.setdefault("salary_min", None)
        patch.setdefault("salary_max", None)
    JobIn.model_validate({**previous, **patch})
    if previous["source_url"]:
        previous["source_url"] = str(previous["source_url"])
    changed = any(previous[key] != value for key, value in patch.items())
    # A new source timestamp/fingerprint alone is an observation, not a content edit.
    changed |= any(
        getattr(item, key) != value for key, value in metadata.items() if key != "source_updated_at"
    )
    expiry = metadata.get("source_expires_at", item.source_expires_at)
    status, basis = listing_state(verification, expiry, now)
    changed |= item.status != status or item.status_basis != basis
    for key, value in {**patch, **metadata}.items():
        setattr(item, key, value)
    item.status, item.status_basis = status, basis
    item.last_seen_at = now
    item.last_verified_at = verification.checked_at
    item.payload_fingerprint = normalized.fingerprint
    item.description_fingerprint = description_digest(item.description)
    if changed and not inserted:
        item.material_updated_at = now
    db.flush()
    flag_probable_duplicates(db, item)
    capture(db, item, old_content, old_status, bool(inserted), run_id)
    return item, "inserted" if inserted else "updated" if changed else "unchanged"


def flag_probable_duplicates(db, item):
    # Require corroborating description + employer + title across different sources.
    # Titles alone never identify duplicates; records/provenance remain independent.
    candidates = db.scalars(
        select(Job)
        .where(
            Job.id != item.id,
            Job.source_id.is_distinct_from(item.source_id),
            Job.description_fingerprint == item.description_fingerprint,
            func.lower(Job.title) == item.title.lower(),
            func.lower(Job.employer) == item.employer.lower(),
        )
        .limit(20)
    )
    for other in candidates:
        if item.location != other.location and item.source_url != other.source_url:
            continue
        a, b = sorted((item.id, other.id))
        db.execute(
            insert(DuplicateCandidate)
            .values(
                job_id=a, other_job_id=b, evidence="employer_title_description_and_location_or_url"
            )
            .on_conflict_do_nothing(constraint="uq_duplicate_pair")
        )
