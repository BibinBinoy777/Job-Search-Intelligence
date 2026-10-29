from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from app.api.schemas import Schema
from app.modules.search.schemas import SearchCriteria


class NotificationPreferencesIn(Schema):
    job_alerts: bool = False
    reminders: bool = True
    in_app: bool = True
    email: bool = False
    timezone: str = Field(default="UTC", max_length=100)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Choose a valid IANA timezone") from None
        return value


class AlertIn(Schema):
    name: str = Field(min_length=1, max_length=100)
    criteria: SearchCriteria = Field(default_factory=SearchCriteria)
    saved_search_id: UUID | None = None
    enabled: bool = True
    include_updates: bool = False
    email: bool = False
    initial_policy: Literal["future_events_only"] = "future_events_only"
    frequency: Literal["immediate"] = "immediate"

    @field_validator("name")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Supply a subscription name")
        return value.strip()

    @model_validator(mode="after")
    def safe_criteria(self):
        if (
            self.criteria.availability_scope != "available"
            or self.criteria.status in {"closed", "expired", "unknown"}
            or self.criteria.match_state in {"stale", "missing", "insufficient"}
        ):
            raise ValueError(
                "Alerts require available active listings and cannot target stale/missing assessments"
            )
        return self


class AlertUpdate(AlertIn):
    expected_revision: int = Field(ge=1)


class AlertOut(Schema):
    id: str
    name: str
    saved_search_id: str | None
    criteria: dict
    enabled: bool
    include_updates: bool
    email: bool
    revision: int
    starts_after: datetime
    created_at: datetime
    updated_at: datetime
    initial_policy: str = "future_events_only"
    frequency: str = "immediate"


class ReminderIn(Schema):
    application_id: UUID
    kind: Literal[
        "follow_up", "interview_preparation", "deadline_review", "application_update", "manual"
    ] = "follow_up"
    local_time: datetime
    timezone: str = Field(default="UTC", max_length=100)
    fold: Literal[0, 1] | None = None
    note: str | None = Field(default=None, max_length=500)
    email: bool = False

    @field_validator("local_time")
    @classmethod
    def wall_clock(cls, value):
        if value.tzinfo is not None:
            raise ValueError(
                "Supply local wall time without an offset and an explicit IANA timezone"
            )
        return value


class ReminderUpdate(ReminderIn):
    expected_revision: int = Field(ge=1)


class ReminderAction(Schema):
    action: Literal["complete", "cancel"]
    expected_revision: int = Field(ge=1)


class ReminderOut(Schema):
    id: str
    application_id: str
    kind: str
    due_at: datetime
    timezone: str
    note: str | None
    email: bool
    status: str
    revision: int
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class NotificationOut(Schema):
    id: str
    category: str
    title: str
    message: str
    href: str
    job_id: str | None
    application_id: str | None
    in_app_status: str
    read_at: datetime | None
    created_at: datetime
    deliveries: list[dict] = Field(default_factory=list)


class ReadIn(Schema):
    read: bool = True


class ReadBatch(Schema):
    ids: list[UUID] = Field(min_length=1, max_length=100)


class SourceScheduleIn(Schema):
    enabled: bool
    interval_hours: int = Field(default=24, ge=24, le=720)
    page_limit: int = Field(default=2, ge=1, le=25)


class ReconcileIn(Schema):
    decision: Literal["delivered", "failed"]
    evidence: str = Field(min_length=10, max_length=200)


class TaskOut(Schema):
    id: str
    kind: str
    status: str
    attempts: int
    retries: int
    due_at: datetime
    lease_until: datetime | None
    error_code: str | None
    outcome: dict
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
