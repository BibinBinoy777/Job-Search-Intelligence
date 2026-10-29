# Matching evaluation and limitations

The offline dataset `data/evaluation/matching-rubric-v1.json` contains 3 synthetic candidate snapshots, 16 synthetic jobs and 4 queries with agent-authored graded expectations and rationales. Independent human review is explicitly false. Fixtures never enter genuine application job storage, and no model is trained on them.

Run from `apps/backend`: `python -m app.modules.matching.evaluation --output ../../docs/matching-evaluation-results.json`. It uses fixed assessment time 2026-10-27 UTC, the versioned deterministic engine, explicit exclusions and a title-only comparator over the same admitted candidate pool. Each query specifies K (3, 3, 2, 3). Relevance is grade > 0; graded NDCG gains are 2^grade - 1. Precision divides by K even for short lists. Recall and NDCG are null when no relevant/ideal gain exists; macro means omit those nulls. Duplicate ranked IDs and invalid K are rejected.

Executed for `evidence-baseline-1.0.1+d5546bafea1c`:

| Diagnostic macro metric | Evidence baseline | Title-only comparator |
|---|---:|---:|
| Precision@query K | 0.750 | 0.375 |
| Recall@query K | 1.000 | 0.500 |
| NDCG@query K | 1.000 | 0.759471 |

The three assessable queries each have Precision/Recall/NDCG 1.0; the incomplete profile intentionally returns no ranking and precision 0, with recall/NDCG undefined. These tiny, implementation-adjacent expectations only diagnose whether the baseline behaves as specified. They are not an independent benchmark, an unbiased comparison, statistical evidence of superiority, real-job accuracy, calibration or hiring probability. The same admitted pool also limits what the title-only comparison establishes. Do not promote these numbers as product-quality validation.

Separate live checks used the 80 genuine persisted Himalayas listings and an explicitly synthetic temporary private candidate. They verified HTTP/UI operation, extraction span integrity, repeat refresh caching and exact replay. They did not establish whether recommendations suit a real person. 70 live pairs were assessable and 10 retained null scores; no fabricated zero was substituted. See `phase3-live-evidence.json` and `phase3-live-integrity.json`.

Future quality work needs consenting real candidate snapshots, independently judged relevance and eligibility labels, ambiguity review, held-out datasets, extraction precision/recall, ranking metrics across sufficient queries, fairness/error slices and prospective user feedback. No such validation or training is claimed complete.
