from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.schemas import JobOut

EligibilityState = Literal[
    "confirmed_compatible", "confirmed_mismatch", "unknown", "not_applicable"
]


class Component(BaseModel):
    value: float | None = Field(ge=0, le=1)
    reason: str
    details: dict[str, Any]


class EligibilityCheck(BaseModel):
    code: str
    status: EligibilityState
    message: str
    evidence: dict[str, Any]


class Eligibility(BaseModel):
    status: EligibilityState
    checks: list[EligibilityCheck]
    excluded: bool
    limitations: list[str]


class Coverage(BaseModel):
    value: float | None = Field(ge=0, le=1)
    supported_units: int
    identified_units: int
    definition: str


class Assessment(BaseModel):
    assessment_status: Literal["assessed", "insufficient_information"]
    score: float | None = Field(ge=0, le=100)
    eligibility: Eligibility
    features: dict[str, Component]
    skills: dict[str, list[dict[str, Any]]]
    evidence_coverage: Coverage
    weight_coverage: float = Field(ge=0, le=1.000001)
    contributing_weights: dict[str, float]
    unavailable_components: list[str]
    normalization: str
    profile_completeness: str
    positive_factors: list[dict[str, Any]]
    concerns: list[dict[str, Any]]
    unknown_information: list[dict[str, Any]]
    data_quality: dict[str, Any]
    ranking_version: str
    config: dict[str, Any]
    score_interpretation: str


class MatchOut(BaseModel):
    id: str
    job: JobOut
    score: float | None
    eligibility_status: EligibilityState
    assessment_status: str
    evidence_coverage: float | None
    ranking_version: str
    config_fingerprint: str
    candidate_fingerprint: str
    job_fingerprint: str
    generated_at: datetime
    is_stale: bool
    stale_reasons: list[str]
    assessment: Assessment


class RefreshIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=200, ge=1, le=200)
    job_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=200)
    after_job_id: UUID | None = None

    @model_validator(mode="after")
    def one_mode(self):
        if self.job_ids and self.after_job_id:
            raise ValueError("Use job_ids or after_job_id, not both")
        return self


class RefreshOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    ranking_version: str
    status: str
    considered: int
    calculated: int
    reused: int
    failed: int
    has_more: bool
    next_job_id: str | None
    errors: list[dict[str, str]]
    started_at: datetime
    finished_at: datetime


class PairOut(BaseModel):
    state: Literal["not_calculated", "current", "stale", "unavailable"]
    match: MatchOut | None
    message: str
