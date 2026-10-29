import re
import unicodedata
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.api.schemas import EmploymentType, JobOut, Schema, WorkMode
from app.modules.matching.schemas import EligibilityState, PairOut

Sort = Literal[
    "recent",
    "text_relevance",
    "candidate_match",
    "published_desc",
    "verified_desc",
    "title",
    "employer",
    "salary_desc",
]


def normalize_query(value):
    return " ".join(re.sub(r"[^\w+#.]+", " ", unicodedata.normalize("NFKC", value).lower()).split())


class SearchCriteria(Schema):
    q: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=250)
    employer: str | None = Field(default=None, max_length=250)
    location: str | None = Field(default=None, max_length=250)
    country: str | None = Field(default=None, max_length=100)
    employment_type: EmploymentType | None = None
    work_arrangement: WorkMode | None = None
    employment_types: list[EmploymentType] = Field(default_factory=list, max_length=5)
    work_arrangements: list[WorkMode] = Field(default_factory=list, max_length=3)
    skills: list[str] = Field(default_factory=list, max_length=10)
    source_id: UUID | None = None
    status: Literal["active", "unknown", "closed", "expired"] | None = None
    availability_scope: Literal["available", "all", "requires_verification"] = "available"
    published_after: datetime | None = None
    updated_after: datetime | None = None
    verified_after: datetime | None = None
    experience_min: float | None = Field(default=None, ge=0, le=80)
    experience_max: float | None = Field(default=None, ge=0, le=80)
    salary_min: float | None = Field(default=None, ge=0, le=999999999999)
    salary_max: float | None = Field(default=None, ge=0, le=999999999999)
    salary_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    salary_period: Literal["hour", "week", "fortnight", "month", "year"] | None = None
    minimum_score: float | None = Field(default=None, ge=0, le=100)
    eligibility: EligibilityState | None = None
    required_coverage: float | None = Field(default=None, ge=0, le=1)
    match_state: Literal["any", "current", "stale", "missing", "insufficient"] = "any"
    sort: Sort = "recent"

    @field_validator("q")
    @classmethod
    def normalized_q(cls, value):
        value = normalize_query(value) if value else None
        if value and len(value.split()) > 12:
            raise ValueError("Search supports at most 12 keyword terms")
        return value or None

    @field_validator("skills")
    @classmethod
    def bounded_skills(cls, values):
        if any(not v.strip() or len(v) > 100 for v in values):
            raise ValueError("Each skill must contain 1–100 characters")
        return list(dict.fromkeys(v.strip() for v in values))

    @model_validator(mode="after")
    def compatible(self):
        if (
            self.salary_min is not None or self.salary_max is not None or self.sort == "salary_desc"
        ) and not (self.salary_currency and self.salary_period):
            raise ValueError("Salary filtering/sorting requires both currency and pay period")
        for lo, hi in [
            (self.salary_min, self.salary_max),
            (self.experience_min, self.experience_max),
        ]:
            if lo is not None and hi is not None and hi < lo:
                raise ValueError("Maximum must be at least minimum")
        if any(
            value is not None and value.tzinfo is None
            for value in [self.published_after, self.updated_after, self.verified_after]
        ):
            raise ValueError("Date filters require a timezone offset")
        return self


class SearchParams(SearchCriteria):
    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=20, ge=1, le=100)


class MatchSummary(Schema):
    state: Literal["current", "stale", "not_calculated"]
    score: float | None = None
    eligibility: EligibilityState | None = None
    assessment_status: str | None = None
    required_coverage: float | None = None
    ranking_version: str | None = None


class SearchPage(Schema):
    items: list[JobOut]
    total: int
    page: int
    page_size: int
    assessments: dict[str, MatchSummary]
    text_relevance: dict[str, float]
    search_version: str = "lexical-1.0"
    notices: list[str]


class Suggestion(Schema):
    kind: Literal["title", "employer", "location", "skill"]
    value: str


class SuggestionsOut(Schema):
    items: list[Suggestion]


class CompareIn(Schema):
    job_ids: list[UUID] = Field(min_length=1, max_length=3)

    @field_validator("job_ids")
    @classmethod
    def distinct(cls, values):
        if len(set(values)) != len(values):
            raise ValueError("Select distinct jobs")
        return values


class ComparisonItem(Schema):
    job: JobOut
    requirements: dict | None
    candidate_assessment: PairOut | None


class ComparisonOut(Schema):
    items: list[ComparisonItem]
    limit: int = 3


class SavedSearchIn(Schema):
    name: str = Field(min_length=1, max_length=100)
    criteria: SearchCriteria

    @field_validator("name")
    @classmethod
    def normalized_name_length(cls, value):
        if len(value.casefold()) > 100:
            raise ValueError("Normalized search name must fit within 100 characters")
        return value


class SavedSearchPatch(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    criteria: SearchCriteria | None = None

    @field_validator("name")
    @classmethod
    def normalized_name_length(cls, value):
        if value is not None and len(value.casefold()) > 100:
            raise ValueError("Normalized search name must fit within 100 characters")
        return value

    @model_validator(mode="after")
    def nonnull(self):
        if (
            any(getattr(self, key) is None for key in self.model_fields_set)
            or not self.model_fields_set
        ):
            raise ValueError("Provide a name or criteria; explicit null is not supported")
        return self


class SavedSearchOut(SavedSearchIn):
    id: str
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None
