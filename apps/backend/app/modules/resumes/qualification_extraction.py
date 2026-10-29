"""Conservative proposals. Values never become profile facts in this module."""

import re
from datetime import date

from app.modules.matching.representations import fingerprint
from app.modules.matching.skills import mentions, negative_mention, normalize_skill, skill_name
from app.modules.resumes.validation import ResumeError

SECTIONS = {
    "skills": "skill",
    "technical skills": "skill",
    "core competencies": "skill",
    "experience": "experience",
    "work experience": "experience",
    "professional experience": "experience",
    "employment history": "experience",
    "education": "education",
    "academic qualifications": "education",
    "certifications": "certification",
    "certificates": "certification",
    "projects": "project",
    "selected projects": "project",
    "summary": "summary",
    "professional summary": "summary",
    "profile": "summary",
    "languages": "language",
}


def dates(text):
    found = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text)
    values = []
    for raw in found[:2]:
        try:
            values.append(date.fromisoformat(raw).isoformat())
        except ValueError:
            values.append(None)
    current = bool(re.search(r"\b(?:present|current|ongoing)\b", text, re.I))
    return {
        "start_date": values[0] if values else None,
        "end_date": None if current else values[1] if len(values) > 1 else None,
        "is_current": True
        if current
        else False
        if len(values) > 1 and values[1] and date.fromisoformat(values[1]) <= date.today()
        else None,
        "date_text": text or None,
    }


def extract(segments):
    proposals = []
    seen = set()
    section = None

    def add(category, value, segment, start, end, warnings=None):
        key = fingerprint({"category": category, "value": value})
        if key in seen:
            return
        seen.add(key)
        if len(proposals) >= 100:
            raise ResumeError("document_limit")
        proposals.append(
            {
                "category": category,
                "original_value": value,
                "fingerprint": key,
                "evidence": {
                    "segment_id": segment["id"],
                    "start": start,
                    "end": end,
                    "section": section,
                },
                "warnings": warnings or [],
            }
        )

    for segment in segments:
        for line in re.finditer(r"[^\r\n]+", segment["text"]):
            raw = line.group()
            text = raw.strip().strip("• ")
            if not text:
                continue
            header = text.strip(":").casefold()
            if header in SECTIONS:
                section = SECTIONS[header]
                continue
            start = line.start() + raw.find(text)
            end = start + len(text)
            # Only qualification sections support skill proposals. An incidental
            # mention in a header/contact/education line is not a qualification.
            skill_mentions = mentions(text) if section in {"skill", "experience", "project"} else {}
            for key, (lo, hi, _) in skill_mentions.items():
                if not negative_mention(text, lo):
                    add(
                        "skill",
                        {"name": skill_name(key), "canonical": normalize_skill(skill_name(key))},
                        segment,
                        start + lo,
                        start + hi,
                    )
            if section == "experience":
                parts = [part.strip() for part in text.split("|")]
                role = re.match(r"^(.{2,200}?)\s+at\s+(.{2,200})$", parts[0])
                if role:
                    title, employer = role.groups()
                    date_text = parts[1] if len(parts) > 1 else ""
                elif len(parts) >= 2 and not re.fullmatch(r"[\d\s–—-]+", parts[1]):
                    title, employer = parts[:2]
                    date_text = parts[2] if len(parts) > 2 else ""
                else:
                    continue
                value = {
                    "title": title,
                    "employer": employer,
                    **dates(date_text),
                    "responsibilities": parts[3] if len(parts) > 3 else None,
                    "achievements": None,
                    "technologies": [
                        skill_name(key)
                        for key, (lo, _, _) in mentions(text).items()
                        if not negative_mention(text, lo)
                    ],
                }
                add(
                    "experience",
                    value,
                    segment,
                    start,
                    end,
                    [
                        "Dates without exact ISO days remain unknown; current roles have no invented end date.",
                        "Unlabeled narrative lines are not silently assigned as achievements.",
                    ],
                )
            elif section == "education":
                parts = [part.strip() for part in text.split("|")]
                if len(parts) < 2:
                    continue
                date_text = parts[2] if len(parts) > 2 else ""
                parsed = dates(date_text)
                completion = (
                    "unknown"
                    if re.search(r"\b(?:not|never|incomplete|uncompleted)\b", text, re.I)
                    else "in_progress"
                    if re.search(r"in progress|expected|pursuing", text, re.I)
                    else "completed"
                    if re.search(r"\b(?:completed|graduated)\b", text, re.I)
                    else "unknown"
                )
                add(
                    "education",
                    {
                        "qualification": parts[0],
                        "institution": parts[1],
                        "field_of_study": None,
                        "start_date": parsed["start_date"],
                        "end_date": parsed["end_date"],
                        "date_text": date_text or None,
                        "completion_status": completion,
                    },
                    segment,
                    start,
                    end,
                    ["A degree mention does not establish completion or credential validity."],
                )
            elif section in {"certification", "project", "language"}:
                if section == "language" and not re.match(
                    r"^(?:English|Hindi|Malayalam|Tamil|Telugu|Kannada|Bengali|Marathi|Gujarati|Punjabi|Urdu|Arabic|French|German|Spanish|Japanese|Korean|Mandarin|Chinese|Portuguese|Russian)\b",
                    text,
                    re.I,
                ):
                    continue
                parts = [part.strip() for part in text.split("|")]
                value = {"name": parts[0], "profile_text": text if len(text) <= 170 else None}
                if section == "certification":
                    value.update(
                        {
                            "issuer": parts[1] if len(parts) > 1 else None,
                            "issue_date_text": parts[2] if len(parts) > 2 else None,
                            "expiry_date_text": parts[3] if len(parts) > 3 else None,
                            "credential_reference": parts[4] if len(parts) > 4 else None,
                            "validity": "not_verified",
                        }
                    )
                if section == "project":
                    value.update(
                        {
                            "description": parts[1] if len(parts) > 1 else None,
                            "responsibilities": parts[2] if len(parts) > 2 else None,
                            "date_text": parts[3] if len(parts) > 3 else None,
                            "technologies": [skill_name(key) for key in mentions(text)],
                        }
                    )
                add(
                    section,
                    value,
                    segment,
                    start,
                    end,
                    [
                        "Review the exact profile text. Source context remains in this extraction; no validity, outcomes or dates are inferred."
                    ],
                )
            elif section == "summary":
                if len(text) > 10000:
                    raise ResumeError("document_limit")
                add(
                    "summary",
                    {"text": text},
                    segment,
                    start,
                    end,
                    [
                        "Source summary text, not a generated rewrite. Existing summary is preserved unless replacement is explicitly chosen."
                    ],
                )
    for proposal in proposals:
        ev = proposal["evidence"]
        segment = next(item for item in segments if item["id"] == ev["segment_id"])
        assert 0 <= ev["start"] < ev["end"] <= len(segment["text"])
    return proposals
