from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.api.schemas import Schema


class CareerFilters(Schema):
    target_role: str | None = Field(default=None, min_length=2, max_length=150)
    origin_role: str | None = Field(default=None, min_length=2, max_length=150)
    location: str | None = Field(default=None, min_length=2, max_length=150)
    source_id: UUID | None = None
    published_after: datetime | None = None
    published_before: datetime | None = None
    requirement_kind: Literal["all", "required", "preferred"] = "all"

    @model_validator(mode="after")
    def valid_range(self):
        for field in ["published_after", "published_before"]:
            value = getattr(self, field)
            if value is not None and value.tzinfo is None:
                raise ValueError("Publication filters require a timezone offset")
        if (
            self.published_after
            and self.published_before
            and self.published_after > self.published_before
        ):
            raise ValueError("Publication range must be ordered")
        for field in ["target_role", "origin_role", "location"]:
            value = getattr(self, field)
            if value is not None:
                value = value.strip()
                if len(value) < 2:
                    raise ValueError("Filters need at least two non-space characters")
                setattr(self, field, value)
        return self


class SkillEvidence(Schema):
    key: str
    name: str
    status: Literal["confirmed", "resume_evidenced", "inferred"]
    used_for_role_overlap: bool
    sources: list[dict]
    note: str


class Listing(Schema):
    id: str
    title: str
    location: str | None
    source_id: str | None
    source_name: str
    published_at: datetime | None
    last_verified_at: datetime | None
    availability: str
    href: str


class RequirementSupport(Schema):
    job_id: str
    category: Literal["required", "preferred"]
    evidence: list[dict]
    extraction: str


class SkillStatistic(Schema):
    key: str
    name: str
    count: int
    required_count: int
    preferred_count: int
    denominator: int
    percentage: float | None
    candidate_status: str
    observation_strength: str
    supporting_listings: list[Listing]
    requirements: list[RequirementSupport]
    support_truncated: bool


class Gap(SkillStatistic):
    priority: int
    priority_reason: str
    relationship: str
    next_action: str
    action_kind: Literal["investigate_or_learn", "review_existing_evidence"]


class Role(Schema):
    id: str
    title: str
    listing_count: int
    overlap: list[str]
    missing_skills: list[str]
    required_skill_count: int
    overlap_ratio: float
    candidate_sources: list[dict]
    additional_requirements: list[dict]
    representative_listings: list[Listing]
    reason: str
    evidence_strength: str
    next_action: str
    limitations: list[str]


class Transition(Schema):
    origin: str
    origin_kind: Literal["recorded_experience", "selected_exploration"]
    origin_evidence: list[dict]
    destination_id: str
    destination: str
    transferable_skills: list[str]
    skills_to_investigate: list[str]
    additional_requirements: list[dict]
    supporting_listings: list[Listing]
    next_steps: list[str]
    evidence_strength: str
    limitations: list[str]


class Resource(Schema):
    title: str
    provider: str | None
    url: str | None
    verification_status: Literal["verified", "verification_stale", "unverified_suggestion"]
    verified_on: str | None
    verification_source: str | None
    verification_evidence: str | None
    level: str


class LearningAction(Schema):
    skill_key: str
    skill: str
    why: str
    practice: str
    action_kind: str
    supporting_job_ids: list[str]
    resources: list[Resource]


class Market(Schema):
    stored_listing_records: int
    scoped_records: int
    excluded_unavailable: int
    analyzed_records: int
    population_truncated: bool
    duplicate_records_excluded: int
    unique_scoped_listings: int
    relevant_listings: int
    listings_with_usable_requirements: int
    denominator_definition: str
    relevance_basis: str
    target_roles: list[str]
    requirement_kind: str
    sources: list[dict]
    locations: list[dict]
    publication_range: dict
    geography_definition: str
    limitations: list[str]


class CareerOut(Schema):
    analysis_version: str
    generated_at: datetime
    input_fingerprint: str
    filters: CareerFilters
    profile_completeness: str
    candidate_skills: list[SkillEvidence]
    origin_roles: list[str]
    market: Market
    skill_statistics: list[SkillStatistic]
    gaps: list[Gap]
    roles: list[Role]
    transitions: list[Transition]
    learning: list[LearningAction]
    notices: list[str]
