# Phase 4 plan and inspected baseline

Extend the existing job service and `/api/v1/jobs` contract, retaining items/total/page/page_size. Baseline: 80 genuine jobs, one source, four ingestion runs, 160 ingestion ledger entries and 80 cached analyses; no candidate/save/application rows. Every Phase 3 source manifest hash matched before edits. Preserve all baseline rows and previous archives.

1. Central validated search criteria, normalized lexical search, database-side combined filters/sorts/counts and bounded page results. Keep text relevance distinct from stored candidate assessments.
2. SQL-checkable exact content/availability/date context on new match results, plus current candidate/config fingerprints. No second matching formula. Old results lacking this extra context require explicit refresh for search scoring.
3. Source-grounded bounded suggestions and comparison of at most three jobs, reusing canonical job presentation and private pair assessments.
4. Owned saved-search definitions (max 50 per candidate), additive migration and query-relevant indexes. No schedules/alerts.
5. Extend current cards/details/discovery with URL state, filters, comparison and saved-search controls, retaining source/freshness and existing saves/tracker.
6. Regression, security, migration, query-plan, genuine-record evaluation/browser and responsive verification; document exact outcomes and package Phase 4. Stop before Phase 5.

No new external services, paid models or frontend state library are needed. Matching quality remains independently unvalidated.

All implementation steps completed and final verification recorded in [phase4-validation.md](phase4-validation.md). During verification 40 listings naturally aged past the existing 24-hour window; all 80 source records remained preserved. No Phase 5 work started.
