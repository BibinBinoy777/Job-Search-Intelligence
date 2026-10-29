import re

from .config import CONFIG
from .skills import mentions, normalize_skill, skill_name

REQUIRED = re.compile(
    r"\b(?:must|require[ds]?|mandatory|essential|minimum|at least|need(?:ed|s)?|proficien(?:t|cy)|expertise in)\b",
    re.I,
)
PREFERRED = re.compile(r"\b(?:preferred|nice.to.have|bonus|desirable|a plus|ideally)\b", re.I)
YEAR = re.compile(
    r"(?P<minimum>\d{1,2}(?:\.\d+)?)\s*(?:(?:-|–|to)\s*(?P<maximum>\d{1,2}(?:\.\d+)?))?\s*\+?\s*years?(?:\s+of)?\s+(?:(?:relevant|professional|commercial|hands.on|industry|related|software|engineering)\s+){0,3}experience",
    re.I,
)
DEGREE = re.compile(r"\b(bachelor(?:['’]s)?|master(?:['’]s)?|ph\.?d\.?|doctorate)\b", re.I)


def evidence(field, text, start, end, kind, section=None):
    return {
        "field": field,
        "start": start,
        "end": end,
        "text": text[start:end],
        "origin": kind,
        "section": section,
    }


def classify(clause, start, end, default):
    before, after = clause[:start], clause[end:]
    if re.search(
        r"\b(?:not required|not necessary|must not|mustn't|no .* required)\b", clause, re.I
    ) or re.search(r"\b(?:not|never)\s+(?:require|need)\s*$", before, re.I):
        return "incidental"
    near_before = before[-90:]
    if PREFERRED.search(near_before) or re.match(
        r"\s*(?:(?:is|are|would be|experience is)\s+)?(?:preferred|a plus|desirable|nice.to.have)",
        after,
        re.I,
    ):
        return "preferred"
    if REQUIRED.search(near_before) or re.match(
        r"\s*(?:(?:is|are|experience is)\s+)?(?:required|mandatory|essential)", after, re.I
    ):
        return "required"
    return default


def analyze_requirements(snapshot):
    skills = {}
    years = []
    qualifications = []
    unknown_constraints = []
    warnings = []
    if snapshot.get("experience_min") is not None:
        years.append(
            {
                "minimum": float(snapshot["experience_min"]),
                "maximum": snapshot.get("experience_max"),
                "kind": "required",
                "scope_skills": [],
                "evidence": {
                    "field": "experience_min",
                    "start": 0,
                    "end": len(str(snapshot["experience_min"])),
                    "text": str(snapshot["experience_min"]),
                    "origin": "structured",
                    "section": None,
                },
            }
        )

    def add(key, kind, ev):
        skills.setdefault(key, {"key": key, "name": skill_name(key), "kind": kind, "evidence": []})
        priority = {"incidental": 0, "preferred": 1, "required": 2}
        if priority[kind] > priority[skills[key]["kind"]]:
            skills[key]["kind"] = kind
        skills[key]["evidence"].append({**ev, "classified_as": kind})

    for i, skill in enumerate(snapshot.get("skills") or []):
        add(
            normalize_skill(skill["name"]),
            skill["kind"],
            {
                "field": f"skills/{i}/name",
                "start": 0,
                "end": len(skill["name"]),
                "text": skill["name"],
                "origin": "structured",
                "section": None,
            },
        )
    for field in ["description", "responsibilities", "qualifications"]:
        text = snapshot.get(field) or ""
        if not text:
            continue
        default = "required" if field == "qualifications" else "incidental"
        section = None
        for line in re.finditer(r"[^\n]+", text):
            original = line.group()
            header = original.strip().strip(":").casefold()
            if len(header) < 90:
                if header in {
                    "requirements",
                    "required skills",
                    "required qualifications",
                    "qualifications",
                    "what you bring",
                    "what we look for",
                    "what you'll need",
                    "what you need",
                    "you have",
                    "minimum qualifications",
                }:
                    default, section = "required", original.strip()
                    continue
                if header in {
                    "preferred",
                    "preferred qualifications",
                    "preferred skills",
                    "nice to have",
                    "bonus",
                    "desirable",
                }:
                    default, section = "preferred", original.strip()
                    continue
                if header in {
                    "about us",
                    "about the company",
                    "benefits",
                    "perks",
                    "responsibilities",
                    "what you'll do",
                    "what you will do",
                    "our tech stack",
                    "our stack",
                    "the role",
                }:
                    default, section = "incidental", original.strip()
                    continue
            for clause in re.finditer(r"[^;]+", original):
                piece = clause.group()
                base = line.start() + clause.start()
                alternatives = bool(re.search(r"\bor\b", piece, re.I)) and len(mentions(piece)) > 1
                if alternatives:
                    warnings.append("alternative_skills_require_review")
                constraint = re.search(
                    r"\b(?:work authorization|authorized to work|right to work|security clearance|citizenship|citizen|licen[cs]e|certification)\b",
                    piece,
                    re.I,
                )
                if (
                    constraint
                    and classify(piece, constraint.start(), constraint.end(), default) == "required"
                ):
                    unknown_constraints.append(
                        {
                            "type": "authorization_or_credential",
                            "evidence": evidence(
                                field,
                                text,
                                base,
                                base + min(len(piece), 400),
                                "deterministic",
                                section,
                            ),
                        }
                    )
                for key, (start, end, _) in mentions(piece).items():
                    kind = classify(piece, start, end, default)
                    if alternatives:
                        kind = "incidental"
                    # Exact supporting sentence/span, never generated quotes.
                    lo, hi = base, base + len(piece)
                    if hi - lo > 400:
                        lo = max(base, base + start - 120)
                        hi = min(base + len(piece), base + end + 180)
                    add(key, kind, evidence(field, text, lo, hi, "deterministic", section))
                for match in YEAR.finditer(piece):
                    kind = classify(piece, match.start(), match.end(), default)
                    if kind == "incidental":
                        continue
                    minimum = float(match["minimum"])
                    maximum = float(match["maximum"]) if match["maximum"] else None
                    if minimum > 60 or maximum is not None and maximum < minimum:
                        warnings.append("ambiguous_experience_range")
                        continue
                    scope = piece[match.end() : match.end() + 90]
                    scope_keys = (
                        list(mentions(scope))
                        if re.match(r"\s*(?:in|with|using)\b", scope, re.I)
                        else []
                    )
                    years.append(
                        {
                            "minimum": minimum,
                            "maximum": maximum,
                            "kind": kind,
                            "scope_skills": scope_keys,
                            "evidence": evidence(
                                field,
                                text,
                                base + match.start(),
                                base + match.end() + len(scope),
                                "deterministic",
                                section,
                            ),
                        }
                    )
                for match in DEGREE.finditer(piece):
                    kind = classify(piece, match.start(), match.end(), default)
                    if kind != "incidental":
                        value = match.group().casefold()
                        level = (
                            "bachelor"
                            if value.startswith("bachelor")
                            else "master"
                            if value.startswith("master")
                            else "doctorate"
                        )
                        qualifications.append(
                            {
                                "level": level,
                                "kind": kind,
                                "equivalent_accepted": bool(
                                    re.search(r"\bor equivalent\b", piece, re.I)
                                ),
                                "evidence": evidence(
                                    field,
                                    text,
                                    base,
                                    base + min(len(piece), 400),
                                    "deterministic",
                                    section,
                                ),
                            }
                        )
    required = [v for v in skills.values() if v["kind"] == "required"]
    preferred = [v for v in skills.values() if v["kind"] == "preferred"]
    incidental = [v for v in skills.values() if v["kind"] == "incidental"]
    return {
        "extractor_version": CONFIG.extractor_version,
        "taxonomy_version": CONFIG.taxonomy_version,
        "required_skills": sorted(required, key=lambda x: x["key"]),
        "preferred_skills": sorted(preferred, key=lambda x: x["key"]),
        "incidental_skills": sorted(incidental, key=lambda x: x["key"]),
        "experience_requirements": list(
            {(r["minimum"], r["maximum"], tuple(r["scope_skills"])): r for r in years}.values()
        ),
        "unknown_constraints": unknown_constraints,
        "qualification_requirements": qualifications,
        "warnings": warnings,
        "description_present": bool((snapshot.get("description") or "").strip()),
        "seniority": next(
            (
                x
                for x in ["principal", "senior", "junior", "intern"]
                if re.search(r"\b" + x + r"\b", snapshot.get("title", ""), re.I)
            ),
            None,
        ),
    }
