from datetime import date, datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    StringConstraints,
    field_validator,
    model_validator,
)

Text100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Text200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
WorkMode = Literal["remote", "hybrid", "on_site"]
EmploymentType = Literal["full_time", "part_time", "contract", "internship", "temporary"]
Status = Literal["interested", "planned", "applied", "interview", "offer", "rejected", "withdrawn"]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", str_strip_whitespace=True)


class Credentials(Schema):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class UserOut(Schema):
    id: str
    email: str
    is_operator: bool = False


class ProfileEdit(Schema):
    name: str | None = Field(default=None, max_length=150)
    headline: str | None = Field(default=None, max_length=240)
    summary: str | None = Field(default=None, max_length=10000)
    qualifications: list[Text200] = Field(default_factory=list, max_length=50)
    certifications: list[Text200] = Field(default_factory=list, max_length=50)
    projects: list[Text200] = Field(default_factory=list, max_length=50)


class SkillIn(Schema):
    name: Text100


class SkillOut(SkillIn):
    id: str


class Dated(Schema):
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date cannot precede start date")
        if self.start_date and self.start_date > date.today():
            raise ValueError("Start date cannot be in the future")
        return self


class ExperienceIn(Dated):
    employer: Text200
    title: Text200
    responsibilities: str | None = Field(default=None, max_length=10000)
    achievements: str | None = Field(default=None, max_length=10000)
    technologies: list[Text100] = Field(default_factory=list, max_length=100)
    is_current: bool | None = None

    @model_validator(mode="after")
    def current_dates(self):
        if self.is_current and self.end_date:
            raise ValueError("A current role must not have an end date")
        return self


class ExperienceOut(ExperienceIn):
    id: str


class EducationIn(Dated):
    institution: Text200
    qualification: Text200
    field_of_study: str | None = Field(default=None, max_length=200)
    completion_status: Literal["unknown", "in_progress", "completed"] = "unknown"


class EducationOut(EducationIn):
    id: str


class PreferencesIn(Schema):
    target_titles: list[Text200] = Field(default_factory=list, max_length=50)
    industries: list[Text100] = Field(default_factory=list, max_length=50)
    locations: list[Text200] = Field(default_factory=list, max_length=50)
    work_arrangements: list[WorkMode] = Field(default_factory=list, max_length=3)
    employment_types: list[EmploymentType] = Field(default_factory=list, max_length=5)
    minimum_salary: float | None = Field(default=None, ge=0, le=999999999999)
    currency: Currency | None = None
    career_level: str | None = Field(default=None, max_length=100)
    relocation: bool | None = None
    current_country: str | None = Field(default=None, min_length=2, max_length=200)

    @model_validator(mode="after")
    def salary_currency(self):
        if self.minimum_salary is not None and self.currency is None:
            raise ValueError("Currency is required with a salary expectation")
        return self


class ProfileOut(ProfileEdit):
    id: str
    skills: list[SkillOut]
    experience: list[ExperienceOut]
    education: list[EducationOut]
    preferences: PreferencesIn | None
    updated_at: datetime


class SourceOut(Schema):
    schedule_hours: int | None = None
    page_limit: int = 2
    id: str
    name: str
    source_type: str
    enabled: bool
    operational_status: str
    last_sync_at: datetime | None
    last_success_at: datetime | None
    error_code: str | None
    adapter_key: str | None = None
    page_limit: int = 2
    schedule_hours: int | None = None
    next_sync_at: datetime | None = None
    last_full_sync_at: datetime | None = None
    not_before_at: datetime | None = None


class JobSkillIn(SkillIn):
    kind: Literal["required", "preferred"]


class JobSkillOut(JobSkillIn):
    id: str


class JobIn(Schema):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=250)]
    employer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=250)]
    description: str = Field(min_length=1, max_length=100000)
    responsibilities: str | None = Field(default=None, max_length=30000)
    qualifications: str | None = Field(default=None, max_length=30000)
    experience_min: float | None = Field(default=None, ge=0, le=80)
    experience_max: float | None = Field(default=None, ge=0, le=80)
    employment_type: EmploymentType | None = None
    work_arrangement: WorkMode | None = None
    location: str | None = Field(default=None, max_length=250)
    salary_min: float | None = Field(default=None, ge=0, le=999999999999)
    salary_max: float | None = Field(default=None, ge=0, le=999999999999)
    salary_currency: Currency | None = None
    salary_period: Literal["hour", "week", "fortnight", "month", "year"] | None = None
    source_id: str | None = Field(default=None, max_length=36)
    external_id: str | None = Field(default=None, min_length=1, max_length=300)
    source_url: HttpUrl | None = None
    published_at: datetime | None = None
    last_verified_at: datetime | None = None
    status: Literal["unknown", "active", "closed", "expired"] = "unknown"
    skills: list[JobSkillIn] = Field(default_factory=list, max_length=100)

    @field_validator("published_at", "last_verified_at")
    @classmethod
    def timezone_required(cls, value):
        if value and value.tzinfo is None:
            raise ValueError("Timezone offset is required")
        return value

    @model_validator(mode="after")
    def consistency(self):
        if self.external_id and not self.source_id:
            raise ValueError("External identity requires a source")
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_max < self.salary_min
        ):
            raise ValueError("Salary maximum must be at least the minimum")
        if (
            self.salary_min is not None or self.salary_max is not None
        ) and not self.salary_currency:
            raise ValueError("Salary currency is required")
        if (
            self.experience_min is not None
            and self.experience_max is not None
            and self.experience_max < self.experience_min
        ):
            raise ValueError("Experience maximum must be at least the minimum")
        return self


class JobOut(JobIn):
    id: str
    skills: list[JobSkillOut]
    source: SourceOut | None
    first_seen_at: datetime
    last_seen_at: datetime
    material_updated_at: datetime
    created_at: datetime
    updated_at: datetime
    is_saved: bool = False
    source_updated_at: datetime | None = None
    source_expires_at: datetime | None = None
    status_basis: str | None = None
    location_restrictions: list[str] | None = None
    timezone_restrictions: list[str | float] | None = None
    source_categories: list[str] | None = None
    availability: str = "not_verified"
    is_available: bool = True

    @model_validator(mode="after")
    def availability_presentation(self):
        from app.ingestion.freshness import present_availability

        return present_availability(self, bool(self.source and self.source.adapter_key))


class SavedOut(Schema):
    id: str
    created_at: datetime
    job: JobOut


class ApplicationIn(Schema):
    job_id: str = Field(min_length=36, max_length=36)
    status: Status = "interested"
    applied_on: date | None = None
    follow_up_on: date | None = None
    notes: str | None = Field(default=None, max_length=10000)
    # Future module resolves this opaque reference within the candidate's private namespace.
    resume_version_ref: str | None = Field(default=None, max_length=100)

    @field_validator("applied_on")
    @classmethod
    def application_date(cls, value):
        if value and value > date.today():
            raise ValueError("Application date cannot be in the future")
        return value


class ApplicationPatch(Schema):
    expected_version: int = Field(ge=1)
    status: Status | None = None
    applied_on: date | None = None
    follow_up_on: date | None = None
    notes: str | None = Field(default=None, max_length=10000)
    correction_reason: str | None = Field(default=None, min_length=3, max_length=500)


class ApplicationOut(ApplicationIn):
    id: str
    version: int
    job: JobOut
    created_at: datetime
    updated_at: datetime


class EventOut(Schema):
    id: str
    application_id: str
    from_status: str | None
    to_status: str
    reason: str | None
    created_at: datetime


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
