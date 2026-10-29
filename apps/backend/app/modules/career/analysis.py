"""Pure sample analysis. Heuristics describe evidence, never employment odds."""

import re
from collections import Counter, defaultdict

from app.modules.matching.representations import ROLE_ALIASES, ROLE_STOP, fingerprint

VERSION = "career-evidence-1.0"


def title_tokens(title):
    text = title.casefold()
    for alias, canonical in ROLE_ALIASES.items():
        text = text.replace(alias, canonical)
    # Keep unknown technology/domain words: the matching vocabulary is useful
    # for relevance, but dropping them would make Java and JavaScript equivalent.
    return set(re.findall(r"[a-z0-9][a-z0-9+#.]*", text)) - ROLE_STOP


def role_matches(title, target):
    tokens = title_tokens(target)
    return tokens <= title_tokens(title) if tokens else target.casefold() in title.casefold()


def role_key(title):
    return " ".join(sorted(title_tokens(title))) or " ".join(title.casefold().split())


def deduplicate(records):
    seen, unique = set(), []
    for record in records:
        snap = record["snapshot"]
        key = fingerprint(
            {
                "title": record["job"].title.casefold(),
                "employer": record["job"].employer.casefold(),
                "location": (record["job"].location or "").casefold(),
                "content": snap,
            }
        )
        if key not in seen:
            unique.append(record)
            seen.add(key)
    return unique, len(records) - len(unique)


def public_listing(job):
    return {
        "id": job.id,
        "title": job.title,
        "location": job.location,
        "source_id": job.source_id,
        "source_name": job.source.name if job.source else "Manual / legacy",
        "published_at": job.published_at,
        "last_verified_at": job.last_verified_at,
        "availability": "recently verified source listing"
        if job.source and job.source.adapter_key
        else "manual / legacy availability not independently verified",
        "href": f"/jobs/{job.id}",
    }


def requirements(record, kind="all"):
    analysis = record["analysis"]
    return [
        (category, skill)
        for category in ["required", "preferred"]
        if kind in {"all", category}
        for skill in analysis[category + "_skills"]
    ]


def strength(count, denominator):
    # Descriptive labels only. Threshold is documented; no statistical inference.
    return "directional signal" if count >= 3 and denominator >= 5 else "limited evidence"


def statistics(records, evidence, kind):
    by_skill = {}
    evidence_by_key = {s["key"]: s for s in evidence}
    for record in records:
        for category, skill in requirements(record, kind):
            item = by_skill.setdefault(
                skill["key"],
                {"key": skill["key"], "name": skill["name"], "required": {}, "preferred": {}},
            )
            item[category][record["job"].id] = (record, skill)
    result = []
    for key, value in by_skill.items():
        merged = {**value["preferred"], **value["required"]}
        entries = list(merged.values())
        candidate = evidence_by_key.get(key)
        result.append(
            {
                "key": key,
                "name": value["name"],
                "count": len(merged),
                "required_count": len(value["required"]),
                "preferred_count": len(value["preferred"]),
                "denominator": len(records),
                "percentage": round(100 * len(merged) / len(records), 1) if records else None,
                "candidate_status": candidate["status"] if candidate else "not_evidenced",
                "observation_strength": strength(len(merged), len(records)),
                "supporting_listings": [public_listing(r["job"]) for r, _ in entries[:20]],
                "requirements": [
                    {
                        "job_id": r["job"].id,
                        "category": "required" if r["job"].id in value["required"] else "preferred",
                        "evidence": skill["evidence"],
                        "extraction": "structured or deterministic source extraction; not independently verified",
                    }
                    for r, skill in entries[:20]
                ],
                "support_truncated": len(entries) > 20,
            }
        )
    return sorted(result, key=lambda s: (-s["required_count"], -s["count"], s["key"]))


def gaps_from(stats, evidence):
    known = {s["key"] for s in evidence if s["used_for_role_overlap"]}
    unconfirmed = {s["key"] for s in evidence if not s["used_for_role_overlap"]}
    names = [s["name"] for s in evidence if s["used_for_role_overlap"]]
    result = []
    for stat in stats:
        if stat["key"] in known:
            continue
        pending = stat["key"] in unconfirmed
        result.append(
            {
                **stat,
                "priority": len(result) + 1,
                "priority_reason": f"{stat['required_count']} required and {stat['preferred_count']} preferred occurrences among {stat['denominator']} relevant distinct listings. Ordered by required count, then total frequency, then skill key; this is a heuristic, not hiring probability.",
                "relationship": f"These listings also provide the context in which to investigate transfer from recorded skills ({', '.join(names[:5])}). Skill relatedness is not established by co-occurrence."
                if names
                else "No recorded skill overlap establishes transferable knowledge; investigate prerequisites first.",
                "next_action": "Review and explicitly confirm or reject the existing resume suggestion before deciding whether to learn this skill."
                if pending
                else f"Check the cited {stat['name']} requirements against your actual experience; add evidence you already have, or plan relevant practice.",
                "action_kind": "review_existing_evidence" if pending else "investigate_or_learn",
            }
        )
    return result


def additional_requirements(records):
    result = []
    for record in records:
        for field in [
            "qualification_requirements",
            "experience_requirements",
            "unknown_constraints",
        ]:
            for item in record["analysis"][field]:
                result.append(
                    {
                        "job_id": record["job"].id,
                        "category": field,
                        "requirement": item,
                        "interpretation": "Source requirement to investigate; candidate satisfaction and credential validity are not established.",
                    }
                )
    return result[:20]


def recommend_roles(records, evidence):
    known = {s["key"]: s for s in evidence if s["used_for_role_overlap"]}
    groups = defaultdict(list)
    for record in records:
        groups[role_key(record["job"].title)].append(record)
    result = []
    for key, group in groups.items():
        skills = {
            skill["key"]: skill["name"] for record in group for _, skill in requirements(record)
        }
        required = {
            skill["key"]
            for record in group
            for category, skill in requirements(record)
            if category == "required"
        }
        overlap = sorted(set(skills) & set(known))
        if not overlap:
            continue
        result.append(
            {
                "id": fingerprint(key)[:16],
                "title": group[0]["job"].title,
                "listing_count": len(group),
                "overlap": [skills[k] for k in overlap],
                "missing_skills": [skills[k] for k in sorted(required - known.keys())],
                "required_skill_count": len(required),
                "overlap_ratio": round(len(overlap) / len(skills), 4),
                "candidate_sources": [
                    {
                        "skill": known[k]["name"],
                        "status": known[k]["status"],
                        "references": known[k]["sources"],
                    }
                    for k in overlap
                ],
                "additional_requirements": additional_requirements(group),
                "representative_listings": [public_listing(r["job"]) for r in group[:20]],
                "reason": f"Recorded evidence overlaps {len(overlap)} of {len(skills)} distinct required/preferred skills in {len(group)} collected listing(s). Similarity of titles alone is not used. Investigate the remaining requirements and eligibility.",
                "evidence_strength": strength(len(group), len(records)),
                "next_action": "Inspect representative listings, verify missing requirements and eligibility, then choose a role to investigate.",
                "limitations": [
                    "Exploration suggestion, not a finding that every requirement is met.",
                    "Title normalization can group seniority variants; individual requirements differ.",
                    "Additional requirement details are limited to the first 20; inspect all representative listings for full wording.",
                ],
            }
        )
    return sorted(
        result,
        key=lambda r: (
            -r["overlap_ratio"],
            -len(r["overlap"]),
            -r["listing_count"],
            r["title"].casefold(),
        ),
    )[:12]


def sample_breakdown(records):
    sources = Counter(
        (r["job"].source_id, r["job"].source.name if r["job"].source else "Manual / legacy")
        for r in records
    )
    locations = Counter(r["job"].location or "Not supplied" for r in records)
    dates = [r["job"].published_at for r in records if r["job"].published_at]
    return {
        "sources": [
            {"id": key[0], "name": key[1], "count": count}
            for key, count in sorted(sources.items(), key=lambda x: str(x[0]))
        ],
        "locations": [{"label": name, "count": count} for name, count in sorted(locations.items())],
        "publication_range": {
            "earliest": min(dates).isoformat() if dates else None,
            "latest": max(dates).isoformat() if dates else None,
            "unknown_count": len(records) - len(dates),
        },
    }
