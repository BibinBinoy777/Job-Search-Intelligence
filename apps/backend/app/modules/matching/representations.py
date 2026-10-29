import hashlib
import json
import re
from datetime import UTC, datetime

from app.api.schemas import ProfileOut


def fingerprint(value):
    def normalized(item):
        return item.astimezone(UTC).isoformat() if isinstance(item, datetime) else str(item)

    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=normalized
        ).encode()
    ).hexdigest()


def candidate_snapshot(profile):
    raw = ProfileOut.model_validate(profile).model_dump(mode="json")
    # Name, user identity, school/employer identity and document-upload state do
    # not affect ranking. Child IDs provide private evidence references only.
    keep = {
        k: raw[k]
        for k in [
            "headline",
            "summary",
            "qualifications",
            "certifications",
            "projects",
            "skills",
            "experience",
            "education",
            "preferences",
        ]
    }
    for key in ["skills", "experience", "education"]:
        keep[key] = sorted(keep[key], key=lambda x: x["id"])
    for item in keep["experience"]:
        item.pop("employer", None)
    for item in keep["education"]:
        item.pop("institution", None)
    return keep


def job_snapshot(job):
    fields = [
        "title",
        "description",
        "responsibilities",
        "qualifications",
        "experience_min",
        "experience_max",
        "employment_type",
        "work_arrangement",
        "location",
        "salary_min",
        "salary_max",
        "salary_currency",
        "salary_period",
        "location_restrictions",
        "timezone_restrictions",
        "source_categories",
    ]
    result = {key: getattr(job, key) for key in fields}
    result["skills"] = sorted(
        [{"name": s.name, "kind": s.kind} for s in job.skills], key=lambda x: (x["kind"], x["name"])
    )
    # Decimal -> JSON number, datetimes -> ISO. This normalized snapshot is the
    # exact public input persisted for old analyses after source text changes.
    for key in ["salary_min", "salary_max"]:
        if result[key] is not None:
            result[key] = float(result[key])
    return result


def job_input_fingerprint(job, content, as_of_date=None):
    return fingerprint(
        {
            "assessment_day": (as_of_date or datetime.now(UTC).date()).isoformat(),
            "content": content,
            "status": job.status,
            "status_basis": job.status_basis,
            "last_verified_at": job.last_verified_at,
            "source_expires_at": job.source_expires_at,
            "source_id": job.source_id,
            "external_id": job.external_id,
        }
    )


ROLE_ALIASES = {
    "software developer": "software engineer",
    "web developer": "web engineer",
    "frontend developer": "frontend engineer",
    "front-end": "frontend",
    "back-end": "backend",
    "full-stack": "fullstack",
    "data analytics": "data analysis",
    "technical support representative": "customer support",
    "customer service representative": "customer support",
}
ROLE_STOP = {
    "senior",
    "junior",
    "lead",
    "principal",
    "staff",
    "intern",
    "entry",
    "level",
    "sr",
    "jr",
    "the",
    "and",
    "of",
    "a",
    "an",
    "at",
    "for",
    "remote",
    "ii",
    "iii",
    "iv",
    "1",
    "2",
    "3",
    "4",
}
ROLE_VOCAB = set(
    "software engineer developer web frontend backend fullstack data analysis analyst scientist science machine learning artificial intelligence automation product project manager management support customer technical sales marketing business operations financial finance accounting accountant designer design ux ui graphic consultant sap specialist security cloud platform systems administrator research researcher writer content editor teacher teaching nurse nursing medical doctor healthcare civil mechanical electrical executive assistant director qa quality assurance tester testing devops mobile android ios python javascript react api implementation solutions success procurement logistics transportation rollout".split()
)


def role_tokens(text):
    text = text.casefold()
    for before, after in ROLE_ALIASES.items():
        text = text.replace(before, after)
    return (set(re.findall(r"[a-z][a-z+#]{1,}", text)) - ROLE_STOP) & ROLE_VOCAB


def role_overlap(a, b):
    first, second = role_tokens(a), role_tokens(b)
    return len(first & second) / len(first | second) if first and second else None
