"""Read-only genuine-record specification evaluation; never an accuracy claim."""

import argparse
import json
import statistics
from pathlib import Path
from time import perf_counter

from sqlalchemy import func, select, text

from app.db.models import Job, JobRequirementAnalysis
from app.db.session import SessionLocal
from app.ingestion.freshness import visible_job_condition
from app.modules.matching.config import CONFIG
from app.modules.matching.representations import job_snapshot
from app.modules.search.query import build_query
from app.modules.search.schemas import SearchParams, normalize_query
from app.modules.search.service import search


def evaluate(db):
    # An absent user is deliberate: evaluate public lexical behavior without
    # loading or disclosing any candidate's qualifications or result history.
    user_id = "offline-search-evaluation-no-candidate"
    jobs = list(db.scalars(select(Job).where(visible_job_condition())).unique())
    stored_count = db.scalar(select(func.count()).select_from(Job))
    historical = search(db, user_id, SearchParams(availability_scope="all", page_size=100))
    assert historical["total"] == stored_count
    if len(jobs) < 2:
        raise ValueError("Collect at least two genuinely available jobs before evaluating")
    first = next(j for j in jobs if 1 <= len(normalize_query(j.title).split()) <= 12)
    cases = []

    def check(name, params, expected):
        outcome = search(db, user_id, SearchParams(page_size=100, **params))
        found = {j.id for j in outcome["items"]}
        assert found == expected, (name, len(found), len(expected))
        cases.append(
            {
                "case": name,
                "expected_count": len(expected),
                "actual_count": len(found),
                "exact_set_agreement": True,
            }
        )

    check(
        "partial-title",
        {"title": first.title[: max(2, len(first.title) // 2)]},
        {
            j.id
            for j in jobs
            if first.title[: max(2, len(first.title) // 2)].lower() in j.title.lower()
        },
    )
    check(
        "employer",
        {"employer": first.employer},
        {j.id for j in jobs if first.employer.lower() in j.employer.lower()},
    )
    current_jobs = {job.id: job for job in jobs}
    cached = {
        row.job_id: row.analysis
        for row in db.scalars(
            select(JobRequirementAnalysis).where(
                JobRequirementAnalysis.job_id.in_(current_jobs),
                JobRequirementAnalysis.extractor_version == CONFIG.extractor_version,
            )
        )
        if row.job_snapshot == job_snapshot(current_jobs[row.job_id])
    }
    identified = [
        item
        for value in cached.values()
        for item in value["required_skills"] + value["preferred_skills"]
    ]
    if identified:
        skill = identified[0]["name"]
        expected = {
            job.id
            for job in jobs
            if any(skill.lower() in item.name.lower() for item in job.skills)
            or any(
                skill.lower() in item["name"].lower()
                or skill.lower().replace(" ", "_") in item["key"].lower()
                for item in cached.get(job.id, {}).get("required_skills", [])
                + cached.get(job.id, {}).get("preferred_skills", [])
            )
        }
        check("source-required-or-preferred-skill", {"skills": [skill]}, expected)
    if first.work_arrangement and first.employment_type:
        check(
            "combined-title-mode-employment",
            {
                "title": first.title,
                "work_arrangement": first.work_arrangement,
                "employment_type": first.employment_type,
            },
            {
                j.id
                for j in jobs
                if first.title.lower() in j.title.lower()
                and j.work_arrangement == first.work_arrangement
                and j.employment_type == first.employment_type
            },
        )
    check("no-results", {"q": "zzphase4unlikelykeywordqxtz"}, set())
    check("missing-assessments-not-zero", {"minimum_score": 0}, set())
    dated = [j for j in jobs if j.published_at]
    check(
        "known-publication-date",
        {"published_after": "2000-01-01T00:00:00Z"},
        {j.id for j in dated if j.published_at.year >= 2000},
    )
    check(
        "USD-annual-salary-only",
        {"salary_min": 1, "salary_currency": "USD", "salary_period": "year"},
        {
            j.id
            for j in jobs
            if j.salary_currency == "USD"
            and j.salary_period == "year"
            and (j.salary_max if j.salary_max is not None else j.salary_min) is not None
            and (j.salary_max if j.salary_max is not None else j.salary_min) >= 1
        },
    )
    query = SearchParams(q=first.title, sort="text_relevance", page_size=100)
    exact = search(db, user_id, query)
    assert normalize_query(exact["items"][0].title) == normalize_query(first.title)
    expected = {j.id for j in jobs if normalize_query(j.title) == normalize_query(first.title)}
    cutoff = len(expected)
    ranked = [j.id for j in exact["items"][:cutoff]]
    lexical_metrics = {
        "definition": "Exact normalized title as specification relevance; not human job relevance",
        "cutoff": cutoff,
        "precision_at_cutoff": len(set(ranked) & expected) / cutoff,
        "recall_exact_titles_at_cutoff": len(set(ranked) & expected) / len(expected),
    }
    pages = []
    for p in range(1, (len(jobs) + 11) // 12 + 1):
        pages.extend(
            j.id
            for j in search(db, user_id, SearchParams(sort="title", page=p, page_size=12))["items"]
        )
    assert len(set(pages)) == len(jobs) and len(pages) == len(jobs)
    repeated = [
        j.id for j in search(db, user_id, SearchParams(sort="title", page_size=100))["items"]
    ]
    assert pages == repeated
    durations = []
    for _ in range(7):
        start = perf_counter()
        search(db, user_id, query)
        durations.append((perf_counter() - start) * 1000)
    stmt = build_query(db, user_id, query).limit(12)
    compiled = str(stmt.compile(db.bind, compile_kwargs={"literal_binds": True}))
    plan = db.execute(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + compiled)).scalar()[0]

    def nodes(node):
        return [node.get("Node Type")] + [
            kind for child in node.get("Plans", []) for kind in nodes(child)
        ]

    return {
        "dataset": "Existing genuinely stored available jobs; no inserted fixtures",
        "genuine_available_jobs": len(jobs),
        "genuine_stored_jobs": stored_count,
        "outside_default_discovery": stored_count - len(jobs),
        "explicit_historical_view_count_verified": historical["total"],
        "case_results": cases,
        "lexical_specification_metrics": lexical_metrics,
        "stable_unique_paginated_jobs": len(pages),
        "local_service_latency_ms": {
            "runs": len(durations),
            "median": round(statistics.median(durations), 2),
            "maximum": round(max(durations), 2),
            "minimum": round(min(durations), 2),
        },
        "query_plan": {
            "planning_ms": plan["Planning Time"],
            "execution_ms": plan["Execution Time"],
            "returned_rows": plan["Plan"]["Actual Rows"],
            "node_types": sorted(set(nodes(plan["Plan"]))),
        },
        "independent_human_relevance_labels": False,
        "limitations": [
            "Tiny one-provider snapshot; timings are local observations, not a load benchmark.",
            "Rules test filter and lexical-order correctness, not candidate suitability or market demand.",
            "Closed/unknown/missing-field and match-invalidation edge cases are covered in isolated PostgreSQL tests when absent in this snapshot.",
            "Phase 3 matching quality remains independently unvalidated.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with SessionLocal() as db:
        result = evaluate(db)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
