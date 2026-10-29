from datetime import timedelta

from sqlalchemy import and_, or_, select

from app.core.security import utcnow
from app.db.models import Job, JobSource


def listing_state(verification, expires_at, now):
    if verification.status == "closed":
        return "closed", verification.basis
    if expires_at and expires_at <= now:
        return "expired", "source_deadline_elapsed"
    return verification.status, verification.basis


def visible_job_condition(now=None):
    now = now or utcnow()
    # Manual/legacy records retain the Phase 1 behavior. Integrated listings must
    # have recent independent availability evidence and a future source deadline.
    integrated = Job.source_id.in_(select(JobSource.id).where(JobSource.adapter_key.is_not(None)))
    available = and_(
        Job.status == "active",
        Job.last_verified_at >= now - timedelta(hours=24),
        or_(Job.source_expires_at.is_(None), Job.source_expires_at > now),
    )
    return or_(~integrated, available)


def present_availability(result, integrated, now=None):
    now = now or utcnow()
    if not integrated:
        result.availability = "not_verified" if result.last_verified_at is None else "checked"
        return result
    if result.source_expires_at and result.source_expires_at <= now:
        result.status = "expired"
        result.status_basis = "source_deadline_elapsed"
    result.is_available = (
        result.status == "active"
        and result.last_verified_at is not None
        and result.last_verified_at >= now - timedelta(hours=24)
    )
    result.availability = (
        "verified_open"
        if result.is_available
        else ("verification_stale" if result.status == "active" else result.status)
    )
    if not result.is_available:
        # Retain identity for private saves/application history while removing
        # unavailable vacancy content and the Apply action from candidate views.
        result.description = "This listing is unavailable or requires a fresh source check. Your private tracking history is preserved."
        result.responsibilities = result.qualifications = None
        result.source_url = None
        result.skills = []
        result.salary_min = result.salary_max = result.salary_currency = result.salary_period = None
        result.experience_min = result.experience_max = None
        result.source_categories = None
    return result
