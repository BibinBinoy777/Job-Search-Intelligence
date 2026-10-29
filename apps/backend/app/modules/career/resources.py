"""Reviewed public-provider metadata, never runtime network access."""

import json
from datetime import date
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[2] / "data" / "career-resources.json"


def learning_for(gaps, today=None):
    today = today or date.today()
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    actions = []
    for gap in gaps[:12]:
        resources = []
        for entry in catalog:
            if gap["key"] not in entry["skills"]:
                continue
            # Verification is a dated identity/content snapshot, never live uptime.
            checked = date.fromisoformat(entry["verified_on"])
            status = "verified" if 0 <= (today - checked).days <= 90 else "verification_stale"
            resources.append(
                {
                    k: entry[k]
                    for k in [
                        "title",
                        "provider",
                        "url",
                        "verified_on",
                        "verification_source",
                        "verification_evidence",
                        "level",
                    ]
                }
                | {"verification_status": status}
            )
        if not resources:
            resources = [
                {
                    "title": f"Investigate official {gap['name']} documentation and prerequisites",
                    "provider": None,
                    "url": None,
                    "verified_on": None,
                    "verification_source": None,
                    "verification_evidence": None,
                    "level": "Choose a starting level after checking your existing experience.",
                    "verification_status": "unverified_suggestion",
                }
            ]
        actions.append(
            {
                "skill_key": gap["key"],
                "skill": gap["name"],
                "why": gap["priority_reason"],
                "practice": gap["next_action"]
                if gap["action_kind"] == "review_existing_evidence"
                else f"Compare your existing work with the cited {gap['name']} requirement; choose one relevant exercise and document what you can demonstrate. Introductory level is optional, not an assumption about you.",
                "action_kind": gap["action_kind"],
                "supporting_job_ids": [r["job_id"] for r in gap["requirements"]],
                "resources": resources,
            }
        )
    return actions
