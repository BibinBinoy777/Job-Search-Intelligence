import hashlib
import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

from pydantic import ValidationError

from app.api.schemas import JobIn
from app.modules.sources.contracts import NormalizedJob, SourceError


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.ignored += 1
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4"} and not self.ignored:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.ignored = max(0, self.ignored - 1)
        if tag in {"p", "div", "li", "h1", "h2", "h3", "h4"} and not self.ignored:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def plain_text(value):
    if not isinstance(value, str):
        raise SourceError("invalid_description")
    parser = PlainText()
    parser.feed(value)
    return re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def identity_url(value):
    if not isinstance(value, str) or len(value) > 300:
        raise SourceError("invalid_source_identity")
    try:
        parts = urlsplit(value)
    except ValueError:
        raise SourceError("invalid_source_identity") from None
    if (
        parts.scheme != "https"
        or parts.netloc != "himalayas.app"
        or parts.query
        or parts.fragment
        or not re.fullmatch(r"/companies/[a-zA-Z0-9_-]+/jobs/[a-zA-Z0-9_-]+", parts.path)
    ):
        raise SourceError("invalid_source_identity")
    return value


def timestamp(value):
    if type(value) not in {int, float}:
        raise SourceError("invalid_source_timestamp")
    try:
        return datetime.fromtimestamp(value, UTC)
    except (OverflowError, OSError, ValueError):
        raise SourceError("invalid_source_timestamp") from None


def normalize_himalayas(raw, source_id):
    if not isinstance(raw, dict):
        raise SourceError("invalid_record_shape")
    identity = identity_url(raw.get("guid"))
    link = raw.get("applicationLink")
    if not isinstance(link, str):
        raise SourceError("missing_application_link")
    try:
        parts = urlsplit(link)
    except ValueError:
        raise SourceError("invalid_application_link") from None
    if (
        parts.scheme != "https"
        or parts.netloc != "himalayas.app"
        or parts.path != urlsplit(identity).path
        or parts.fragment
    ):
        raise SourceError("invalid_application_link")
    data = {
        "title": raw.get("title"),
        "employer": raw.get("companyName"),
        "description": plain_text(raw.get("description")),
        "source_id": source_id,
        "external_id": identity,
        "source_url": link,
        "work_arrangement": "remote",
    }
    mapping = {
        "Full Time": "full_time",
        "Part Time": "part_time",
        "Contractor": "contract",
        "Temporary": "temporary",
        "Intern": "internship",
    }
    if raw.get("employmentType") in mapping:
        data["employment_type"] = mapping[raw["employmentType"]]
    has_salary = raw.get("minSalary") is not None or raw.get("maxSalary") is not None
    if has_salary:
        for source, target in [
            ("minSalary", "salary_min"),
            ("maxSalary", "salary_max"),
            ("currency", "salary_currency"),
        ]:
            if raw.get(source) is not None:
                data[target] = raw[source]
    periods = {
        "hourly": "hour",
        "weekly": "week",
        "fortnightly": "fortnight",
        "monthly": "month",
        "annual": "year",
    }
    if has_salary and raw.get("salaryPeriod") in periods:
        data["salary_period"] = periods[raw["salaryPeriod"]]
    elif has_salary:
        raise SourceError("unknown_salary_period")
    metadata = {}
    if "locationRestrictions" in raw and raw["locationRestrictions"] is not None:
        locations = raw["locationRestrictions"]
        if not isinstance(locations, list) or len(locations) > 300:
            raise SourceError("invalid_location_restrictions")
        names = []
        for loc in locations:
            name = loc.get("name") if isinstance(loc, dict) else loc
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
                raise SourceError("invalid_location_restrictions")
            names.append(name.strip())
        metadata["location_restrictions"] = names
        location = ", ".join(names) if names else "Worldwide"
        data["location"] = (
            location
            if len(location) <= 250
            else ", ".join(names[:2])[:220] + f" (+{len(names) - 2} countries)"
        )
    for source, target in [
        ("timezoneRestrictions", "timezone_restrictions"),
        ("categories", "source_categories"),
    ]:
        if source in raw and raw[source] is not None:
            value = raw[source]
            if (
                not isinstance(value, list)
                or len(value) > 300
                or any(not isinstance(v, (str, int, float)) or isinstance(v, bool) for v in value)
            ):
                raise SourceError("invalid_restrictions_or_categories")
            if source == "categories" and any(not isinstance(v, str) for v in value):
                raise SourceError("invalid_categories")
            metadata[target] = value
    for source, target in [("pubDate", "source_updated_at"), ("expiryDate", "source_expires_at")]:
        if raw.get(source) is not None:
            metadata[target] = timestamp(raw[source])
    try:
        canonical = JobIn.model_validate(data)
    except ValidationError:
        raise SourceError("canonical_validation_failed") from None
    return NormalizedJob(canonical, metadata, fingerprint(raw))
