from datetime import date

from .eligibility import COUNTRIES, country
from .representations import role_overlap
from .skills import mentions


def skill_comparison(candidate, analysis):
    def compare(items):
        return [
            {
                "key": item["key"],
                "name": item["name"],
                "candidate_evidence": candidate["skills"].get(item["key"], []),
                "job_evidence": item["evidence"],
                "state": "evidenced" if item["key"] in candidate["skills"] else "not_evidenced",
            }
            for item in items
        ]

    return {
        "required": compare(analysis["required_skills"]),
        "preferred": compare(analysis["preferred_skills"]),
        "ambiguous_mentions": analysis["incidental_skills"],
    }


def component(value, reason, details=None):
    return {
        "value": round(value, 6) if value is not None else None,
        "reason": reason,
        "details": details or {},
    }


def merged_years(intervals):
    if not intervals:
        return None
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return sum((end - start).days for start, end in merged) / 365.25


def experience_feature(candidate, job, analysis, as_of):
    contexts = []
    requirements = [r for r in analysis["experience_requirements"] if r["kind"] == "required"]
    job_keys = {
        s["key"]
        for s in analysis["required_skills"]
        + analysis["preferred_skills"]
        + analysis["incidental_skills"]
    }
    relevant = []
    intervals = []
    undated = []
    for record in candidate["experience"]:
        text = " ".join(
            [
                record.get("title") or "",
                record.get("responsibilities") or "",
                record.get("achievements") or "",
                *record.get("technologies", []),
            ]
        )
        keys = set(mentions(text))
        # Recorded role or technology overlap establishes contextual relevance,
        # not automatic equivalence of all employment to required experience.
        role = role_overlap(record["title"], job.get("title", ""))
        if (role is not None and role >= 0.5) or keys & job_keys:
            relevant.append({"id": record["id"], "keys": keys, "record": record})
            contexts.append(
                {
                    "path": f"experience/{record['id']}",
                    "matched_context_skills": sorted(keys & job_keys),
                    "role_overlap": role,
                }
            )
    for item in relevant:
        record = item["record"]
        if any(
            r["scope_skills"] and not set(r["scope_skills"]) <= item["keys"] for r in requirements
        ):
            continue
        if (
            record.get("start_date")
            and record.get("end_date")
            and date.fromisoformat(record["end_date"]) <= as_of
        ):
            intervals.append(
                (date.fromisoformat(record["start_date"]), date.fromisoformat(record["end_date"]))
            )
        else:
            undated.append(record["id"])
    years = merged_years(intervals)
    minimum = max((r["minimum"] for r in requirements), default=None)
    if minimum is not None and years is not None:
        value = min(1, years / minimum) if minimum > 0 else 1
        return component(
            value,
            "documented_relevant_years_lower_bound",
            {
                "documented_years": round(years, 2),
                "required_minimum": minimum,
                "evidence": contexts,
                "undated_records": undated,
                "requirements": requirements,
            },
        )
    project_keys = set()
    for text in candidate["projects"]:
        project_keys.update(mentions(text))
    support_keys = set().union(*(x["keys"] for x in relevant)) if relevant else set()
    support_keys |= project_keys
    overlap = job_keys & support_keys
    if minimum is None and overlap and job_keys:
        return component(
            len(overlap) / len(job_keys),
            "responsibility_or_project_technology_overlap_not_years",
            {
                "matched_context_skills": sorted(overlap),
                "evidence": contexts,
                "project_evidence": candidate["projects"],
                "documented_years": round(years, 2) if years is not None else None,
            },
        )
    return component(
        None,
        "relevant_years_not_established"
        if minimum is not None
        else "insufficient_experience_context",
        {
            "documented_years": round(years, 2) if years is not None else None,
            "required_minimum": minimum,
            "evidence": contexts,
            "undated_records": undated,
            "project_context_skills": sorted(overlap),
        },
    )


def calculate_features(candidate, job, analysis, comparison, as_of):
    features = {}
    for group, key in [("required", "required_skills"), ("preferred", "preferred_skills")]:
        items = comparison[group]
        if items and candidate["skills"]:
            matched = sum(bool(x["candidate_evidence"]) for x in items)
            features[key] = component(
                matched / len(items),
                "recorded_skill_evidence_coverage",
                {"matched": matched, "identified": len(items)},
            )
        else:
            features[key] = component(
                None,
                "no_identified_requirements"
                if not items
                else "candidate_skill_evidence_unavailable",
            )
    features["experience"] = experience_feature(candidate, job, analysis, as_of)
    roles = [
        (role_overlap(role["text"], job.get("title", "")), role) for role in candidate["roles"]
    ]
    roles = [(value, role) for value, role in roles if value is not None]
    best = max(roles, key=lambda x: (x[0], x[1]["path"])) if roles else None
    features["role"] = component(
        best[0] if best else None,
        "recognized_role_token_overlap" if best else "role_information_unavailable",
        {"candidate": best[1] if best else None, "job_title": job.get("title")},
    )
    prefs = candidate["preferences"]
    location_checks = []
    if prefs.get("work_arrangements") and job.get("work_arrangement"):
        location_checks.append(
            {
                "kind": "work_arrangement",
                "value": int(job["work_arrangement"] in prefs["work_arrangements"]),
                "candidate": prefs["work_arrangements"],
                "job": job["work_arrangement"],
            }
        )
    if prefs.get("locations"):
        preferred = {country(x) for x in prefs["locations"]}
        allowed = {country(x) for x in job.get("location_restrictions") or []}
        if job.get("location_restrictions") == []:
            location_checks.append(
                {
                    "kind": "preferred_location",
                    "value": 1,
                    "basis": "source_worldwide",
                    "candidate": prefs["locations"],
                }
            )
        elif preferred <= COUNTRIES and allowed and allowed <= COUNTRIES:
            location_checks.append(
                {
                    "kind": "preferred_location",
                    "value": int(bool(preferred & allowed)),
                    "candidate": prefs["locations"],
                    "job": job["location_restrictions"],
                }
            )
        elif job.get("location") and job["location"].casefold() in {
            x.casefold() for x in prefs["locations"]
        }:
            location_checks.append(
                {
                    "kind": "preferred_location",
                    "value": 1,
                    "basis": "exact_location_label",
                    "candidate": prefs["locations"],
                    "job": job["location"],
                }
            )
    features["location"] = component(
        sum(c["value"] for c in location_checks) / len(location_checks)
        if location_checks
        else None,
        "known_location_preferences_only" if location_checks else "location_compatibility_unknown",
        {"checks": location_checks, "eligibility_separate": True},
    )
    preference_checks = []
    unknown = []
    if prefs.get("employment_types") and job.get("employment_type"):
        preference_checks.append(
            {
                "kind": "employment_type",
                "value": int(job["employment_type"] in prefs["employment_types"]),
                "candidate": prefs["employment_types"],
                "job": job["employment_type"],
            }
        )
    if prefs.get("minimum_salary") is not None:
        bound = (
            job.get("salary_max") if job.get("salary_max") is not None else job.get("salary_min")
        )
        if (
            job.get("salary_period") == "year"
            and job.get("salary_currency") == prefs.get("currency")
            and bound is not None
        ):
            preference_checks.append(
                {
                    "kind": "annual_salary_disclosed_bound",
                    "value": int(bound >= prefs["minimum_salary"]),
                    "candidate": prefs["minimum_salary"],
                    "job_bound": bound,
                    "currency": prefs["currency"],
                }
            )
        else:
            unknown.append(
                "Salary compatibility is unknown: missing or incomparable currency/pay period."
            )
    if prefs.get("industries"):
        unknown.append(
            "Reliable job-industry classification is unavailable; source categories are not treated as industry evidence."
        )
    if prefs.get("career_level") and analysis.get("seniority"):
        wanted = prefs["career_level"]
        junior = {"student", "entry_level", "early_career"}
        senior = {"senior", "leadership"}
        compatible = (wanted in junior and analysis["seniority"] in {"junior", "intern"}) or (
            wanted in senior and analysis["seniority"] in {"senior", "principal"}
        )
        preference_checks.append(
            {
                "kind": "career_level_preference",
                "value": int(compatible),
                "candidate": wanted,
                "job": analysis["seniority"],
                "limitation": "A stated career preference, not proof of experience or ability.",
            }
        )
    features["preferences"] = component(
        sum(c["value"] for c in preference_checks) / len(preference_checks)
        if preference_checks
        else None,
        "known_preferences_only" if preference_checks else "preferences_unavailable",
        {"checks": preference_checks, "unknown": unknown},
    )
    units = (
        len(comparison["required"])
        + len(comparison["preferred"])
        + len([r for r in analysis["experience_requirements"] if r["kind"] == "required"])
        + len([r for r in analysis["qualification_requirements"] if r["kind"] == "required"])
        + len(analysis.get("unknown_constraints", []))
    )
    supported = sum(
        bool(i["candidate_evidence"]) for i in comparison["required"] + comparison["preferred"]
    )
    if (
        any(r["kind"] == "required" for r in analysis["experience_requirements"])
        and features["experience"]["value"] is not None
    ):
        supported += len(
            [r for r in analysis["experience_requirements"] if r["kind"] == "required"]
        )
    return features, {
        "value": supported / units if units else None,
        "supported_units": supported,
        "identified_units": units,
        "definition": "positively evidenced or quantitatively assessable identified requirement units; not a probability or complete extraction coverage",
    }
