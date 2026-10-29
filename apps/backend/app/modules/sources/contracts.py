from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.api.schemas import JobIn


@dataclass(frozen=True)
class SourcePage:
    records: list[Any]
    next_cursor: str | None


@dataclass(frozen=True)
class NormalizedJob:
    data: JobIn
    metadata: Mapping[str, Any]
    fingerprint: str


@dataclass(frozen=True)
class Verification:
    status: str
    basis: str
    checked_at: datetime


class SourceError(Exception):
    """Safe diagnostic codes only; never provider bodies or headers."""

    def __init__(self, code: str, retry_at: datetime | None = None):
        self.code = code
        self.retry_at = retry_at
        super().__init__(code)


class JobSourceAdapter(Protocol):
    key: str

    def fetch_jobs(self, criteria: Mapping[str, Any], cursor: str | None = None) -> SourcePage: ...
    def normalize_job(self, raw_job: Mapping[str, Any], source_id: str) -> NormalizedJob: ...
    def get_source_identity(self, raw_job: Mapping[str, Any]) -> str: ...
    def verify_job(self, identity: str) -> Verification: ...
