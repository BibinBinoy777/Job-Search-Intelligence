from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from app.core.security import utcnow
from app.modules.sources.contracts import SourceError, SourcePage, Verification
from app.modules.sources.normalization import identity_url, normalize_himalayas
from app.modules.sources.transport import JsonTransport


class HimalayasAdapter:
    key = "himalayas"

    def __init__(self, transport=None):
        self.transport = transport or JsonTransport()

    def fetch_jobs(self, criteria: Mapping[str, Any], cursor=None):
        if set(criteria) - {"limit"}:
            raise SourceError("unsupported_criteria")
        limit = criteria.get("limit", 20)
        if type(limit) is not int or not 1 <= limit <= 20:
            raise SourceError("invalid_page_limit")
        if cursor is not None and (not isinstance(cursor, str) or not 1 <= len(cursor) <= 2048):
            raise SourceError("invalid_cursor")
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        _, payload = self.transport.get("/jobs/api", params)
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("jobs"), list)
            or len(payload["jobs"]) > limit
        ):
            raise SourceError("invalid_page_shape")
        next_cursor = payload.get("nextCursor")
        if next_cursor is not None and (
            not isinstance(next_cursor, str) or not next_cursor or len(next_cursor) > 2048
        ):
            raise SourceError("invalid_page_cursor")
        if next_cursor and not payload["jobs"]:
            raise SourceError("empty_continuation_page")
        return SourcePage(payload["jobs"], next_cursor)

    def get_source_identity(self, raw_job):
        if not isinstance(raw_job, dict):
            raise SourceError("invalid_record_shape")
        return identity_url(raw_job.get("guid"))

    def normalize_job(self, raw_job, source_id):
        return normalize_himalayas(raw_job, source_id)

    def verify_job(self, identity):
        identity_url(identity)
        status, payload = self.transport.get(
            "/jobs/api" + urlsplit(identity).path, allow_status=(404, 410)
        )
        if status == 410:
            return Verification("closed", "single_job_api_closed", utcnow())
        if status == 404:
            return Verification("unknown", "single_job_api_not_found", utcnow())
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("job"), dict)
            or payload["job"].get("guid") != identity
        ):
            raise SourceError("invalid_verification_response")
        return Verification("active", "single_job_api_open", utcnow())
