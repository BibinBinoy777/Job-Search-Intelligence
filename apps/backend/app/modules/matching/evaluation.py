"""Offline synthetic rubric evaluation. Never inserts jobs or trains a model."""

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from .config import CONFIG
from .engine import evaluate
from .representations import role_overlap
from .requirements import analyze_requirements


def metrics(ranked, grades, k):
    if k < 1 or len(ranked) != len(set(ranked)):
        raise ValueError("K must be positive and ranked identifiers unique")
    top = ranked[:k]
    relevant = {key for key, value in grades.items() if value >= 2}
    hits = len(relevant & set(top))

    def dcg(values):
        return sum((2**grade - 1) / math.log2(index + 2) for index, grade in enumerate(values))

    ideal = dcg(sorted(grades.values(), reverse=True)[:k])
    return {
        "precision_at_k": hits / k,
        "recall_at_k": hits / len(relevant) if relevant else None,
        "ndcg_at_k": dcg([grades.get(key, 0) for key in top]) / ideal if ideal else None,
    }


def job_input(raw, now):
    base = {
        "description": "",
        "responsibilities": None,
        "qualifications": None,
        "skills": [],
        "experience_min": None,
        "experience_max": None,
        "employment_type": "full_time",
        "work_arrangement": "remote",
        "location": None,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "salary_period": None,
        "location_restrictions": [],
        "timezone_restrictions": None,
        "source_categories": None,
        "source_expires_at": None,
        "status": "active",
        "last_verified_at": now,
        "status_basis": "synthetic_fixture",
    }
    base.update(raw)
    return base


def run_evaluation(dataset):
    now = datetime(2026, 10, 27, tzinfo=UTC)
    jobs = {raw["id"]: job_input(raw, now) for raw in dataset["jobs"]}
    results = []
    for query in dataset["queries"]:
        candidate = dataset["candidates"][query["candidate"]]
        ranked = []
        for job_id in query["grades"]:
            job = jobs[job_id]
            if (
                job["status"] in {"closed", "expired"}
                or job.get("integrated")
                and (job["status"] != "active" or job["last_verified_at"] is None)
            ):
                continue
            outcome = evaluate(candidate, job, analyze_requirements(job), now)
            if not outcome["eligibility"]["excluded"] and outcome["score"] is not None:
                ranked.append((outcome["score"], job_id))
        ranked_ids = [key for _, key in sorted(ranked, key=lambda item: (-item[0], item[1]))]
        title_only = sorted(
            ranked_ids,
            key=lambda key: (
                -max(
                    (
                        role_overlap(title, jobs[key]["title"]) or 0
                        for title in (candidate.get("preferences") or {}).get("target_titles", [])
                    ),
                    default=0,
                ),
                key,
            ),
        )
        results.append(
            {
                "query": query["id"],
                "k": query["k"],
                "ranking": ranked_ids,
                "metrics": metrics(ranked_ids, query["grades"], query["k"]),
                "title_only_metrics": metrics(title_only, query["grades"], query["k"]),
            }
        )

    def mean(name, key):
        vals = [r[name][key] for r in results if r[name][key] is not None]
        return sum(vals) / len(vals) if vals else None

    return {
        "ranking_version": CONFIG.identity,
        "dataset_version": dataset["version"],
        "independent_human_review": dataset["independent_human_review"],
        "labels_authored_by": dataset["labels_authored_by"],
        "purpose": "synthetic specification/rubric diagnostic; not labor-market accuracy or hiring probability",
        "queries": results,
        "macro_metrics": {
            key: mean("metrics", key) for key in ["precision_at_k", "recall_at_k", "ndcg_at_k"]
        },
        "title_only_macro_metrics": {
            key: mean("title_only_metrics", key)
            for key in ["precision_at_k", "recall_at_k", "ndcg_at_k"]
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).resolve().parents[5] / "data/evaluation/matching-rubric-v1.json",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_evaluation(json.loads(args.dataset.read_text(encoding="utf-8")))
    content = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    print(content)


if __name__ == "__main__":
    main()
