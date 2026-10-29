from datetime import timedelta

COUNTRIES = {
    name.casefold()
    for name in [
        "India",
        "United States",
        "United Kingdom",
        "Canada",
        "Australia",
        "New Zealand",
        "Germany",
        "France",
        "Spain",
        "Italy",
        "Netherlands",
        "Belgium",
        "Ireland",
        "Portugal",
        "Poland",
        "Romania",
        "Ukraine",
        "Switzerland",
        "Austria",
        "Sweden",
        "Norway",
        "Denmark",
        "Finland",
        "Greece",
        "Czech Republic",
        "Hungary",
        "Singapore",
        "Japan",
        "China",
        "South Korea",
        "Indonesia",
        "Malaysia",
        "Philippines",
        "Thailand",
        "Vietnam",
        "Brazil",
        "Mexico",
        "Argentina",
        "Colombia",
        "Chile",
        "Peru",
        "Guatemala",
        "Costa Rica",
        "South Africa",
        "Nigeria",
        "Kenya",
        "Egypt",
        "United Arab Emirates",
        "Saudi Arabia",
        "Israel",
        "Turkey",
        "Pakistan",
        "Bangladesh",
        "Sri Lanka",
        "Nepal",
    ]
}
COUNTRY_ALIASES = {
    "us": "united states",
    "usa": "united states",
    "united states of america": "united states",
    "uk": "united kingdom",
    "great britain": "united kingdom",
    "in": "india",
    "de": "germany",
    "ca": "canada",
    "au": "australia",
    "nz": "new zealand",
    "fr": "france",
    "es": "spain",
    "it": "italy",
    "nl": "netherlands",
    "ie": "ireland",
    "ro": "romania",
    "pl": "poland",
    "sg": "singapore",
    "br": "brazil",
    "mx": "mexico",
    "uae": "united arab emirates",
    "czechia": "czech republic",
    "türkiye": "turkey",
}


def country(value):
    text = " ".join(value.split()).casefold()
    return COUNTRY_ALIASES.get(text, text)


def availability(job, now):
    if job.get("status") in {"closed", "expired"}:
        return {
            "code": "listing_unavailable",
            "status": "confirmed_mismatch",
            "message": "The listing is explicitly closed or expired.",
            "evidence": {"status": job["status"], "basis": job.get("status_basis")},
        }
    if job.get("source_expires_at") and job["source_expires_at"] <= now:
        return {
            "code": "source_deadline_elapsed",
            "status": "confirmed_mismatch",
            "message": "The recorded source deadline has elapsed.",
            "evidence": {"source_expires_at": job["source_expires_at"].isoformat()},
        }
    checked = job.get("last_verified_at")
    if checked and checked < now - timedelta(hours=24):
        return {
            "code": "availability_stale",
            "status": "unknown",
            "message": "Availability evidence is older than the 24-hour window.",
            "evidence": {"last_verified_at": checked.isoformat()},
        }
    if job.get("status") == "active" and checked:
        return {
            "code": "availability_verified",
            "status": "confirmed_compatible",
            "message": "The source confirmed availability within the freshness window.",
            "evidence": {"last_verified_at": checked.isoformat(), "basis": job.get("status_basis")},
        }
    return {
        "code": "availability_unknown",
        "status": "unknown",
        "message": "Current availability has not been established.",
        "evidence": {"status": job.get("status", "unknown")},
    }


def evaluate_eligibility(candidate, job, analysis, skills, now):
    checks = [availability(job, now)]
    restrictions = job.get("location_restrictions")
    current = candidate["preferences"].get("current_country")
    if restrictions == []:
        checks.append(
            {
                "code": "location_worldwide",
                "status": "confirmed_compatible",
                "message": "The source lists no country restriction.",
                "evidence": {"location_restrictions": []},
            }
        )
    elif restrictions:
        allowed = {country(x) for x in restrictions}
        residence = country(current) if current else None
        known = bool(residence in COUNTRIES and allowed <= COUNTRIES)
        state = (
            "confirmed_compatible"
            if known and residence in allowed
            else "confirmed_mismatch"
            if known
            else "unknown"
        )
        checks.append(
            {
                "code": "country_restriction",
                "status": state,
                "message": "Compare the voluntarily recorded current country with explicit source restrictions. Preferences and relocation willingness are not proof of residence or work authorization.",
                "evidence": {
                    "candidate_path": "preferences/current_country",
                    "current_country": current,
                    "location_restrictions": restrictions,
                },
            }
        )
    else:
        checks.append(
            {
                "code": "country_unknown",
                "status": "unknown",
                "message": "Reliable country restrictions are not supplied. Remote work alone does not establish worldwide eligibility.",
                "evidence": {},
            }
        )
    for item in skills["required"]:
        checks.append(
            {
                "code": "required_skill_evidence",
                "status": "confirmed_compatible" if item["candidate_evidence"] else "unknown",
                "message": f"{item['name']}: {'documented evidence found' if item['candidate_evidence'] else 'not evidenced in the available profile; this does not prove absence'}.",
                "evidence": {
                    "key": item["key"],
                    "candidate": item["candidate_evidence"],
                    "job": item["job_evidence"],
                },
            }
        )
    for requirement in analysis["qualification_requirements"]:
        if requirement["kind"] == "required":
            checks.append(
                {
                    "code": "formal_qualification_review",
                    "status": "unknown",
                    "message": "A formal qualification is stated. Degree field, equivalency and credential validity require review; no missing qualification is asserted.",
                    "evidence": {
                        "job": requirement["evidence"],
                        "candidate_education": candidate["education"],
                        "candidate_qualifications": candidate["qualifications"],
                    },
                }
            )
    if any(x["kind"] == "required" for x in analysis["experience_requirements"]):
        checks.append(
            {
                "code": "experience_requirement_review",
                "status": "unknown",
                "message": "Documented relevant years are a lower bound, not an assertion that the candidate has no additional experience. Review the experience component.",
                "evidence": {"requirements": analysis["experience_requirements"]},
            }
        )
    for constraint in analysis.get("unknown_constraints", []):
        checks.append(
            {
                "code": "explicit_constraint_requires_review",
                "status": "unknown",
                "message": "An explicit authorization, clearance or credential condition needs review. It is not inferred from your name, residence, preferences or demographics.",
                "evidence": constraint,
            }
        )
    state = (
        "confirmed_mismatch"
        if any(c["status"] == "confirmed_mismatch" for c in checks)
        else "unknown"
        if any(c["status"] == "unknown" for c in checks)
        else "confirmed_compatible"
    )
    return {
        "status": state,
        "checks": checks,
        "excluded": state == "confirmed_mismatch",
        "limitations": [
            "This is an evidence assessment, not legal work-authorization verification.",
            "Unrecognized hard requirements and credential equivalencies require manual review.",
        ],
    }
