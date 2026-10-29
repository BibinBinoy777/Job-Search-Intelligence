# Phase 3 implementation plan

1. Inspect actual Phase 2 files, schema, source data and tests; record preservation baseline. No matching implementation exists beyond protocols, and the 80 real jobs have no structured skill rows.
2. Add a versioned deterministic matching module: conservative skill aliases, candidate evidence, requirement spans, eligibility, independent features and transparent scoring. No paid AI/embeddings or trained ranker.
3. Add a nullable voluntary current-country preference, cached job analyses, private versioned match results and bounded refresh history through an additive migration.
4. Expose authenticated own-candidate recommendations, status, pair explanations and synchronous bounded refresh with fingerprint invalidation and deterministic ordering.
5. Extend the existing UI with recommendations, evidence details, honest refresh/stale states and existing save/application flows.
6. Add isolated tests, a clearly synthetic rubric-based evaluation dataset/harness, real-record browser verification and preservation/security/build checks.
7. Document weights, applicability/coverage, reproducibility, unknowns, evaluation limitations and exact observed results. Review/package source and stop at Phase 3.

No independent human relevance labels are currently available. Agent-authored synthetic evaluation labels will be disclosed as test expectations, not real-world accuracy evidence or training data.

Completed and verified on 2026-10-28 (Asia/Calcutta). See [completion report](phase3-validation.md). Independent recommendation-quality validation remains outstanding; Phase 4 was not started.
