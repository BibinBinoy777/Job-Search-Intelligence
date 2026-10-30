import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.security import utcnow


def uid():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class User(Identity, Timestamps, Base):
    __tablename__ = "users"
    deletion_pending: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_operator: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Profile(Identity, Timestamps, Base):
    __tablename__ = "candidate_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str | None] = mapped_column(String(150))
    headline: Mapped[str | None] = mapped_column(String(240))
    summary: Mapped[str | None] = mapped_column(Text)
    qualifications: Mapped[list] = mapped_column(JSON, default=list)
    certifications: Mapped[list] = mapped_column(JSON, default=list)
    projects: Mapped[list] = mapped_column(JSON, default=list)
    skills: Mapped[list["CandidateSkill"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    experience: Mapped[list["Experience"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    education: Mapped[list["Education"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    preferences: Mapped["Preferences | None"] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class CandidateSkill(Identity, Base):
    __tablename__ = "candidate_skills"
    __table_args__ = (UniqueConstraint("profile_id", "normalized_name", name="uq_candidate_skill"),)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    normalized_name: Mapped[str] = mapped_column(String(100))


class Experience(Identity, Base):
    __tablename__ = "candidate_experience"
    __table_args__ = (
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="ck_experience_dates",
        ),
    )
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    employer: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    responsibilities: Mapped[str | None] = mapped_column(Text)
    achievements: Mapped[str | None] = mapped_column(Text)
    technologies: Mapped[list] = mapped_column(JSON, default=list)
    is_current: Mapped[bool | None] = mapped_column(Boolean)


class Education(Identity, Base):
    __tablename__ = "candidate_education"
    __table_args__ = (
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="ck_education_dates",
        ),
    )
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    institution: Mapped[str] = mapped_column(String(200))
    qualification: Mapped[str] = mapped_column(String(200))
    field_of_study: Mapped[str | None] = mapped_column(String(200))
    completion_status: Mapped[str] = mapped_column(
        String(30), default="unknown", server_default="unknown"
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)


class Preferences(Base):
    __tablename__ = "candidate_preferences"
    __table_args__ = (
        CheckConstraint(
            "minimum_salary IS NULL OR minimum_salary >= 0", name="ck_preference_salary"
        ),
    )
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    target_titles: Mapped[list] = mapped_column(JSON, default=list)
    industries: Mapped[list] = mapped_column(JSON, default=list)
    locations: Mapped[list] = mapped_column(JSON, default=list)
    work_arrangements: Mapped[list] = mapped_column(JSON, default=list)
    employment_types: Mapped[list] = mapped_column(JSON, default=list)
    minimum_salary: Mapped[float | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    career_level: Mapped[str | None] = mapped_column(String(100))
    relocation: Mapped[bool | None] = mapped_column(Boolean)
    current_country: Mapped[str | None] = mapped_column(String(200))


class JobSource(Identity, Timestamps, Base):
    __tablename__ = "job_sources"
    name: Mapped[str] = mapped_column(String(200), unique=True)
    source_type: Mapped[str] = mapped_column(String(50))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    operational_status: Mapped[str] = mapped_column(String(50), default="not_integrated")
    error_code: Mapped[str | None] = mapped_column(String(100))
    adapter_key: Mapped[str | None] = mapped_column(String(50))
    page_limit: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    schedule_hours: Mapped[int | None] = mapped_column(Integer)
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_full_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    not_before_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("page_limit BETWEEN 1 AND 25", name="ck_source_page_limit"),
        CheckConstraint(
            "schedule_hours IS NULL OR schedule_hours >= 24", name="ck_source_schedule"
        ),
    )


class Job(Identity, Timestamps, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_job_source_identity"),
        CheckConstraint("salary_min IS NULL OR salary_min >= 0", name="ck_job_salary_min"),
        CheckConstraint("salary_max IS NULL OR salary_max >= 0", name="ck_job_salary_max"),
        CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_max >= salary_min",
            name="ck_job_salary_order",
        ),
        CheckConstraint(
            "experience_min IS NULL OR experience_min >= 0", name="ck_job_experience_min"
        ),
        CheckConstraint(
            "experience_max IS NULL OR experience_max >= 0", name="ck_job_experience_max"
        ),
        CheckConstraint(
            "experience_min IS NULL OR experience_max IS NULL OR experience_max >= experience_min",
            name="ck_job_experience_order",
        ),
        CheckConstraint("status IN ('unknown','active','closed','expired')", name="ck_job_status"),
        Index("ix_jobs_title", "title"),
        Index("ix_jobs_location", "location"),
        Index("ix_jobs_filters", "employment_type", "work_arrangement"),
        Index("ix_jobs_last_verified", "last_verified_at"),
    )
    source_id: Mapped[str | None] = mapped_column(ForeignKey("job_sources.id"), index=True)
    external_id: Mapped[str | None] = mapped_column(String(300))
    event_sequence: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    title: Mapped[str] = mapped_column(String(250))
    employer: Mapped[str] = mapped_column(String(250))
    description: Mapped[str] = mapped_column(Text)
    responsibilities: Mapped[str | None] = mapped_column(Text)
    qualifications: Mapped[str | None] = mapped_column(Text)
    experience_min: Mapped[float | None]
    experience_max: Mapped[float | None]
    employment_type: Mapped[str | None] = mapped_column(String(50))
    work_arrangement: Mapped[str | None] = mapped_column(String(50))
    location: Mapped[str | None] = mapped_column(String(250))
    salary_min: Mapped[float | None] = mapped_column(Numeric(14, 2))
    salary_max: Mapped[float | None] = mapped_column(Numeric(14, 2))
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    salary_period: Mapped[str | None] = mapped_column(String(20))
    source_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    material_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(20), default="unknown", index=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    payload_fingerprint: Mapped[str | None] = mapped_column(String(64))
    description_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    status_basis: Mapped[str | None] = mapped_column(String(60))
    location_restrictions: Mapped[list | None] = mapped_column(JSON)
    timezone_restrictions: Mapped[list | None] = mapped_column(JSON)
    source_categories: Mapped[list | None] = mapped_column(JSON)
    skills: Mapped[list["JobSkill"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    source: Mapped["JobSource | None"] = relationship(lazy="joined")


class JobSkill(Identity, Base):
    __tablename__ = "job_skills"
    __table_args__ = (
        UniqueConstraint("job_id", "normalized_name", "kind", name="uq_job_skill"),
        CheckConstraint("kind IN ('required','preferred')", name="ck_job_skill_kind"),
    )
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    normalized_name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20))


class SavedJob(Identity, Base):
    __tablename__ = "saved_jobs"
    __table_args__ = (UniqueConstraint("profile_id", "job_id", name="uq_saved_job"),)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    job: Mapped[Job] = relationship(lazy="joined")


STATUSES = ("interested", "planned", "applied", "interview", "offer", "rejected", "withdrawn")


class Application(Identity, Timestamps, Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("profile_id", "job_id", name="uq_application_job"),
        UniqueConstraint("id", "profile_id", name="uq_application_owner"),
        CheckConstraint(f"status IN {STATUSES}", name="ck_application_status"),
    )
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="interested", index=True)
    applied_on: Mapped[date | None] = mapped_column(Date)
    follow_up_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    # Opaque private reference for a future resume module; no resume access is exposed.
    resume_version_ref: Mapped[str | None] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": version}
    job: Mapped[Job] = relationship(lazy="joined")


class ApplicationEvent(Identity, Base):
    __tablename__ = "application_events"
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class AuditEvent(Identity, Base):
    __tablename__ = "audit_events"
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IngestionRun(Identity, Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','completed','limited','partial','failed','interrupted')",
            name="ck_run_status",
        ),
        Index(
            "uq_active_source_run",
            "source_id",
            unique=True,
            postgresql_where=text("status IN ('queued','running')"),
        ),
        CheckConstraint(
            "fetched = accepted + duplicates + rejected + skipped", name="ck_run_fetched_accounting"
        ),
        CheckConstraint(
            "accepted = inserted + updated + unchanged", name="ck_run_accepted_accounting"
        ),
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("job_sources.id"), index=True)
    requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    root_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("ingestion_runs.id", name="fk_ingestion_root_run")
    )
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_spawned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    trigger: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    start_cursor: Mapped[str | None] = mapped_column(Text)
    next_cursor: Mapped[str | None] = mapped_column(Text)
    max_pages: Mapped[int] = mapped_column(Integer)
    pages: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    fetched: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    accepted: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    inserted: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    unchanged: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    duplicates: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rejected: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    skipped: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    retried: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    errors: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(60))
    source: Mapped[JobSource] = relationship(lazy="joined")


class IngestionRecord(Identity, Base):
    __tablename__ = "ingestion_records"
    __table_args__ = (
        UniqueConstraint("run_id", "page_number", "record_number", name="uq_ingestion_record"),
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="CASCADE"), index=True
    )
    page_number: Mapped[int] = mapped_column(Integer)
    record_number: Mapped[int] = mapped_column(Integer)
    identity_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"))
    outcome: Mapped[str] = mapped_column(String(20))
    error_code: Mapped[str | None] = mapped_column(String(60))


class JobEvent(Identity, Base):
    __tablename__ = "job_events"
    __table_args__ = (UniqueConstraint("job_id", "sequence", "kind", name="uq_job_event_version"),)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("ingestion_runs.id", ondelete="SET NULL"))
    sequence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(30))
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    resulting_status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class AlertSubscription(Identity, Timestamps, Base):
    __tablename__ = "alert_subscriptions"
    __table_args__ = (UniqueConstraint("profile_id", "normalized_name", name="uq_alert_name"),)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    saved_search_id: Mapped[str | None] = mapped_column(
        ForeignKey("saved_searches.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(100))
    normalized_name: Mapped[str] = mapped_column(String(100))
    criteria: Mapped[dict] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    include_updates: Mapped[bool] = mapped_column(Boolean, default=False)
    email: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    starts_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    job_alerts: Mapped[bool] = mapped_column(Boolean, default=False)
    reminders: Mapped[bool] = mapped_column(Boolean, default=True)
    in_app: Mapped[bool] = mapped_column(Boolean, default=True)
    email: Mapped[bool] = mapped_column(Boolean, default=False)
    timezone: Mapped[str] = mapped_column(String(100), default="UTC")


class ApplicationReminder(Identity, Timestamps, Base):
    __tablename__ = "application_reminders"
    __table_args__ = (
        ForeignKeyConstraint(
            ["application_id", "profile_id"],
            ["applications.id", "applications.profile_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('scheduled','notified','completed','cancelled')", name="ck_reminder_status"
        ),
    )
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    application_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    timezone: Mapped[str] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(String(500))
    email: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AutomationTask(Identity, Base):
    __tablename__ = "automation_tasks"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_automation_task_key"),
        CheckConstraint(
            "status IN ('queued','running','retry_scheduled','completed','failed','cancelled')",
            name="ck_automation_task_status",
        ),
    )
    kind: Mapped[str] = mapped_column(String(30))
    dedupe_key: Mapped[str] = mapped_column(String(180))
    event_id: Mapped[str | None] = mapped_column(ForeignKey("job_events.id", ondelete="CASCADE"))
    reminder_id: Mapped[str | None] = mapped_column(
        ForeignKey("application_reminders.id", ondelete="SET NULL")
    )
    reminder_revision: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    outcome: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(Identity, Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_notification_event"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(180))
    category: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(String(1000))
    href: Mapped[str] = mapped_column(String(200))
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    application_id: Mapped[str | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL")
    )
    event_id: Mapped[str | None] = mapped_column(ForeignKey("job_events.id", ondelete="SET NULL"))
    subscription_ids: Mapped[list] = mapped_column(JSON, default=list)
    reminder_id: Mapped[str | None] = mapped_column(
        ForeignKey("application_reminders.id", ondelete="SET NULL")
    )
    reminder_revision: Mapped[int | None] = mapped_column(Integer)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("ingestion_runs.id", ondelete="SET NULL"))
    in_app_status: Mapped[str] = mapped_column(String(20), default="pending")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class NotificationOutbox(Identity, Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        UniqueConstraint("notification_id", "channel", name="uq_notification_channel"),
    )
    notification_id: Mapped[str] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeliveryAttempt(Identity, Base):
    __tablename__ = "notification_attempts"
    __table_args__ = (UniqueConstraint("outbox_id", "number", name="uq_delivery_attempt"),)
    outbox_id: Mapped[str] = mapped_column(
        ForeignKey("notification_outbox.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30))
    error_code: Mapped[str | None] = mapped_column(String(60))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AutomationHeartbeat(Base):
    __tablename__ = "automation_heartbeat"
    key: Mapped[str] = mapped_column(String(30), primary_key=True)
    last_tick_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DuplicateCandidate(Identity, Base):
    __tablename__ = "duplicate_candidates"
    __table_args__ = (UniqueConstraint("job_id", "other_job_id", name="uq_duplicate_pair"),)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    other_job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    evidence: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JobRequirementAnalysis(Identity, Base):
    __tablename__ = "job_requirement_analyses"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "content_fingerprint", "extractor_version", name="uq_requirement_analysis"
        ),
    )
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    extractor_version: Mapped[str] = mapped_column(String(80))
    job_snapshot: Mapped[dict] = mapped_column(JSON)
    analysis: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MatchResult(Identity, Base):
    __tablename__ = "match_results"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "job_id",
            "candidate_fingerprint",
            "job_fingerprint",
            "ranking_version",
            name="uq_match_inputs",
        ),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_match_score"),
        CheckConstraint(
            "evidence_coverage IS NULL OR (evidence_coverage >= 0 AND evidence_coverage <= 1)",
            name="ck_match_evidence_coverage",
        ),
    )
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("job_requirement_analyses.id"))
    candidate_fingerprint: Mapped[str] = mapped_column(String(64))
    job_fingerprint: Mapped[str] = mapped_column(String(64))
    ranking_version: Mapped[str] = mapped_column(String(80), index=True)
    config_fingerprint: Mapped[str] = mapped_column(String(64))
    candidate_snapshot: Mapped[dict] = mapped_column(JSON)
    job_context: Mapped[dict | None] = mapped_column(JSON)
    assessment_day: Mapped[date | None] = mapped_column(Date)
    score: Mapped[float | None]
    eligibility_status: Mapped[str] = mapped_column(String(40))
    evidence_coverage: Mapped[float | None]
    assessment_status: Mapped[str] = mapped_column(String(40))
    result: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class MatchingRefresh(Identity, Base):
    __tablename__ = "matching_refreshes"
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    ranking_version: Mapped[str] = mapped_column(String(80))
    candidate_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30))
    considered: Mapped[int] = mapped_column(Integer)
    calculated: Mapped[int] = mapped_column(Integer)
    reused: Mapped[int] = mapped_column(Integer)
    failed: Mapped[int] = mapped_column(Integer)
    has_more: Mapped[bool] = mapped_column(Boolean)
    next_job_id: Mapped[str | None] = mapped_column(String(36))
    errors: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SavedSearch(Identity, Timestamps, Base):
    __tablename__ = "saved_searches"
    __table_args__ = (
        UniqueConstraint("profile_id", "normalized_name", name="uq_saved_search_name"),
        CheckConstraint("length(name) BETWEEN 1 AND 100", name="ck_saved_search_name"),
    )
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    normalized_name: Mapped[str] = mapped_column(String(100))
    criteria: Mapped[dict] = mapped_column(JSON)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Resume(Identity, Timestamps, Base):
    __tablename__ = "resumes"
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(180))
    version_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="uploaded")


class ResumeVersion(Identity, Base):
    __tablename__ = "resume_versions"
    __table_args__ = (
        UniqueConstraint("resume_id", "number", name="uq_resume_version"),
        CheckConstraint("size_bytes > 0", name="ck_resume_size"),
    )
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(180))
    storage_ref: Mapped[str] = mapped_column(String(100), unique=True)
    detected_type: Mapped[str] = mapped_column(String(10))
    size_bytes: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))
    scan_status: Mapped[str] = mapped_column(String(40), default="not_configured")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ResumeExtraction(Identity, Base):
    __tablename__ = "resume_extractions"
    __table_args__ = (
        UniqueConstraint("version_id", "extractor_version", name="uq_resume_extraction"),
    )
    version_id: Mapped[str] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="CASCADE"), index=True
    )
    extractor_version: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="processing")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    segments: Mapped[list] = mapped_column(JSON, default=list)
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(60))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResumeProposal(Identity, Base):
    __tablename__ = "resume_proposals"
    __table_args__ = (UniqueConstraint("extraction_id", "fingerprint", name="uq_resume_proposal"),)
    extraction_id: Mapped[str] = mapped_column(
        ForeignKey("resume_extractions.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(30))
    original_value: Mapped[dict] = mapped_column(JSON)
    reviewed_value: Mapped[dict | None] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64))
    evidence: Mapped[dict] = mapped_column(JSON)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    review_state: Mapped[str] = mapped_column(String(30), default="pending")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_target: Mapped[dict | None] = mapped_column(JSON)


class ResumeConfirmation(Identity, Base):
    __tablename__ = "resume_confirmations"
    __table_args__ = (
        UniqueConstraint("extraction_id", "request_key", name="uq_resume_confirmation"),
    )
    extraction_id: Mapped[str] = mapped_column(
        ForeignKey("resume_extractions.id", ondelete="CASCADE"), index=True
    )
    request_key: Mapped[str] = mapped_column(String(36))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RecoveryToken(Base):
    __tablename__ = "recovery_tokens"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
