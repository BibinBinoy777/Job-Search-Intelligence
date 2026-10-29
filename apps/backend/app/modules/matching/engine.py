from .candidate import analyze_candidate
from .config import CONFIG
from .eligibility import evaluate_eligibility
from .features import calculate_features, skill_comparison


def evaluate(snapshot, job, analysis, now, config=CONFIG):
    candidate = analyze_candidate(snapshot)
    comparison = skill_comparison(candidate, analysis)
    eligibility = evaluate_eligibility(candidate, job, analysis, comparison, now)
    features, coverage = calculate_features(candidate, job, analysis, comparison, now.date())
    weights = dict(config.weights)
    contributing = {
        key: weights[key] for key, value in features.items() if value["value"] is not None
    }
    weight = sum(contributing.values())
    professional = any(
        features[key]["value"] is not None
        for key in ["required_skills", "preferred_skills", "experience", "role"]
    )
    assessable = (
        candidate["professional_evidence_present"]
        and professional
        and analysis["description_present"]
    )
    score = (
        round(
            100 * sum(contributing[key] * features[key]["value"] for key in contributing) / weight,
            2,
        )
        if assessable and weight
        else None
    )
    missing = [item["name"] for item in comparison["required"] if not item["candidate_evidence"]]
    matched = [item["name"] for item in comparison["required"] if item["candidate_evidence"]]
    positives = []
    concerns = []
    unknown = []
    if matched:
        positives.append(
            {
                "code": "required_skill_evidence",
                "text": f"Recorded profile evidence supports {len(matched)} of {len(comparison['required'])} identified required skills.",
                "skills": matched,
            }
        )
    if missing:
        concerns.append(
            {
                "code": "required_skills_not_evidenced",
                "text": "These required skills are not evidenced in the available profile; this does not prove that you lack them.",
                "skills": missing,
            }
        )
    if features["role"]["value"] is not None and features["role"]["value"] > 0:
        positives.append(
            {
                "code": "role_context_overlap",
                "text": "Recorded target/previous role terminology overlaps the vacancy title.",
                "candidate": features["role"]["details"]["candidate"],
                "job_title": job["title"],
            }
        )
    for key, feature in features.items():
        if feature["value"] is None:
            unknown.append({"code": key + "_unavailable", "text": feature["reason"]})
        elif key in {"location", "preferences"} and feature["value"] < 1:
            concerns.append(
                {
                    "code": key + "_preference_difference",
                    "text": "A stated preference differs from the job; this is not automatically a hard eligibility rejection.",
                    "details": feature["details"],
                }
            )
    unknown.extend(
        {"code": "preference_unknown", "text": text}
        for text in features["preferences"]["details"].get("unknown", [])
    )
    unknown.append(
        {
            "code": "extraction_scope",
            "text": "Only recognized explicit/section-based requirements are extracted. Unrecognized qualifications, seniority details and work authorization need manual review.",
        }
    )
    if not assessable:
        unknown.append(
            {
                "code": "insufficient_information",
                "text": "Add recorded skills, relevant experience or projects to enable a professional relevance assessment. A target role alone is insufficient; a resume upload is not required.",
            }
        )
    return {
        "assessment_status": "assessed" if score is not None else "insufficient_information",
        "score": score,
        "eligibility": eligibility,
        "features": features,
        "skills": comparison,
        "evidence_coverage": coverage,
        "weight_coverage": round(weight, 6),
        "contributing_weights": contributing,
        "unavailable_components": [key for key in weights if key not in contributing],
        "normalization": "Weighted mean over available components. Missing components change the score basis; compare coverage and component lists alongside scores.",
        "profile_completeness": candidate["completeness"],
        "positive_factors": positives,
        "concerns": concerns,
        "unknown_information": unknown,
        "data_quality": {
            "description_present": analysis["description_present"],
            "availability": eligibility["checks"][0],
            "required_skill_count": len(comparison["required"]),
            "preferred_skill_count": len(comparison["preferred"]),
            "warnings": analysis["warnings"],
        },
        "ranking_version": config.identity,
        "config": config.manifest(),
        "score_interpretation": "Recorded relevance on a 0–100 scale, not interview/offer probability or proof that every requirement is met.",
    }
