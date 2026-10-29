from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.api.schemas import Schema

ReviewState = Literal["pending", "accepted", "edited_accepted", "rejected", "needs_clarification"]


class VersionOut(Schema):
    id: str
    number: int
    filename: str
    detected_type: str
    size_bytes: int
    checksum: str
    scan_status: str
    created_at: datetime
    extraction_id: str | None = None
    extraction_status: str | None = None


class ResumeOut(Schema):
    id: str
    name: str
    status: str
    version_count: int
    created_at: datetime
    updated_at: datetime
    versions: list[VersionOut]
    latest_extraction_id: str | None
    latest_successful_extraction_id: str | None


class ProcessIn(Schema):
    version_id: UUID


class ProposalValue(Schema):
    name: str | None = Field(default=None, max_length=200)
    canonical: str | None = Field(default=None, max_length=200)
    employer: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool | None = None
    date_text: str | None = Field(default=None, max_length=200)
    responsibilities: str | None = Field(default=None, max_length=10000)
    achievements: str | None = Field(default=None, max_length=10000)
    technologies: list[str] = Field(default_factory=list, max_length=100)
    institution: str | None = Field(default=None, max_length=200)
    qualification: str | None = Field(default=None, max_length=200)
    field_of_study: str | None = Field(default=None, max_length=200)
    completion_status: Literal["unknown", "in_progress", "completed"] = "unknown"
    issuer: str | None = Field(default=None, max_length=200)
    issue_date_text: str | None = Field(default=None, max_length=200)
    expiry_date_text: str | None = Field(default=None, max_length=200)
    credential_reference: str | None = Field(default=None, max_length=200)
    validity: Literal["not_verified"] = "not_verified"
    description: str | None = Field(default=None, max_length=10000)
    profile_text: str | None = Field(default=None, max_length=200)
    text: str | None = Field(default=None, max_length=10000)


class ReviewItem(Schema):
    id: UUID
    decision: ReviewState
    value: ProposalValue | None = None

    @model_validator(mode="after")
    def edited_value(self):
        if (self.decision == "edited_accepted") != (self.value is not None):
            raise ValueError(
                "An edited acceptance requires an explicit edited value; other decisions retain the source proposal"
            )
        return self


class ReviewIn(Schema):
    expected_revision: int = Field(ge=0)
    items: list[ReviewItem] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique(self):
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("Review distinct proposal IDs")
        return self


class ConfirmIn(Schema):
    request_key: UUID
    expected_revision: int = Field(ge=0)
    expected_profile_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    item_ids: list[UUID] = Field(min_length=1, max_length=100)
    resolutions: dict[str, Literal["skip", "add_separate", "replace_summary"]] = Field(
        default_factory=dict, max_length=100
    )

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.item_ids)) != len(self.item_ids):
            raise ValueError("Confirm distinct proposal IDs")
        if set(self.resolutions) - {str(item) for item in self.item_ids}:
            raise ValueError("Conflict resolutions must refer to selected proposals")
        return self


class ProposalOut(Schema):
    id: str
    category: str
    original_value: dict
    reviewed_value: dict | None
    review_state: str
    warnings: list[str]
    evidence: dict
    applied_at: datetime | None
    applied_target: dict | None


class ExtractionOut(Schema):
    id: str
    version_id: str
    extractor_version: str
    status: str
    revision: int
    attempts: int
    started_at: datetime
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None
    quality: dict
    proposals: list[ProposalOut]


class PreviewOut(Schema):
    extraction_id: str
    revision: int
    profile_fingerprint: str
    items: list[dict]
    unresolved_count: int


class ConfirmOut(Schema):
    confirmation_id: str
    changes: list[dict]
    unresolved_count: int
    matching_requires_refresh: bool
    status: str


class DeleteOut(Schema):
    status: Literal["deleted", "deletion_pending"]
