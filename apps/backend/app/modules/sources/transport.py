import json
import socket
import time
from datetime import timedelta
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.core.config import settings
from app.core.security import utcnow
from app.modules.sources.contracts import SourceError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class JsonTransport:
    """Fixed-origin, bounded JSON. Tests inject transport/time, never credentials."""

    ORIGIN = "https://himalayas.app"

    def __init__(
        self, opener=None, sleep=time.sleep, clock=time.monotonic, on_retry=None, on_request=None
    ):
        self.opener = opener or build_opener(NoRedirect()).open
        self.sleep = sleep
        self.clock = clock
        self.on_retry = on_retry or (lambda: None)
        self.on_request = on_request or (lambda: None)
        self.last_request = None

    def get(self, path, params=None, allow_status=()):
        if not path.startswith("/jobs/api") or ".." in path or "?" in path or "#" in path:
            raise SourceError("destination_rejected")
        url = self.ORIGIN + path + ("?" + urlencode(params) if params else "")
        headers = {
            "Accept": "application/json",
            "User-Agent": "JobSearchIntelligence/0.2 (permitted job API integration)",
        }
        if settings.himalayas_api_key:
            headers["Authorization"] = "Bearer " + settings.himalayas_api_key.get_secret_value()
        for attempt in range(settings.ingestion_attempts):
            if self.last_request is not None:
                self.sleep(max(0, 1.1 - (self.clock() - self.last_request)))
            self.last_request = self.clock()
            self.on_request()
            delay = min(2**attempt, 10)
            retry_at = None
            try:
                with self.opener(
                    Request(url, headers=headers), timeout=settings.ingestion_timeout_seconds
                ) as response:
                    if response.headers.get_content_type() != "application/json":
                        raise SourceError("unexpected_content_type")
                    raw = bytearray()
                    deadline = self.clock() + 40
                    while True:
                        chunk = response.read(65536)
                        if not chunk:
                            break
                        raw.extend(chunk)
                        if len(raw) > settings.ingestion_max_bytes:
                            raise SourceError("response_too_large")
                        if self.clock() > deadline:
                            raise SourceError("response_deadline_exceeded")
                    try:
                        return response.status, json.loads(raw)
                    except (ValueError, UnicodeDecodeError):
                        raise SourceError("invalid_json") from None
            except HTTPError as exc:
                status = exc.code
                retry_after = exc.headers.get("Retry-After")
                exc.close()
                if status in allow_status:
                    return status, None
                if status not in {408, 429, 500, 502, 503, 504}:
                    raise SourceError(
                        "provider_auth_rejected"
                        if status in {401, 403}
                        else "provider_http_rejected"
                    ) from None
                code = "rate_limited" if status == 429 else "provider_unavailable"
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:
                        try:
                            delay = max(
                                delay,
                                (parsedate_to_datetime(retry_after) - utcnow()).total_seconds(),
                            )
                        except (TypeError, ValueError, OverflowError):
                            delay = max(delay, 60)
                if status == 429:
                    delay = max(delay, 60 if retry_after is None else 0)
                retry_at = utcnow() + timedelta(seconds=delay)
            except (URLError, TimeoutError, socket.timeout, OSError):
                code = "network_timeout_or_failure"
            if attempt + 1 >= settings.ingestion_attempts or delay > 30:
                raise SourceError(code, retry_at)
            self.on_retry()
            self.sleep(delay)
        raise SourceError("retry_budget_exhausted")
