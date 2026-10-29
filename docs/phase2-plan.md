# Phase 2 implementation plan

**Completed locally.** Four live source runs, migration/preservation checks, 73 backend tests, 14 frontend tests, isolated and genuine-data browser workflows, production build, formatting/lint and both advisory audits passed. See [phase2-validation.md](phase2-validation.md). Phase 3 remains unstarted.

1. Inspect the actual Phase 1 source, database, migrations, routes, tests and UI; preserve existing records and interfaces.
2. Verify official source access/terms. Selected candidate: Himalayas public browse + single-job API, with attribution and applicationLink preservation. Validate live response differences rather than assuming the OpenAPI schema is exact.
3. Add an additive reliability migration: source configuration/next-run metadata, run ledger/record outcomes, provenance and conservative duplicate-review relationships.
4. Build typed adapter/HTTP transport, normalization, validation, identity persistence, freshness and ingestion orchestration as separate responsibilities.
5. Provide a protected operator CLI, database-backed same-source coordination, recoverable page commits, bounded retries and an optional scheduler. Keep API requests independent of network ingestion.
6. Expose source health/run history and extend persisted PostgreSQL filters and the existing candidate UI, preserving Phase 1 interactions.
7. Test failures, counters, repeat/concurrent ingestion, freshness and authorization; run regression/unit/browser/build/migration checks. Execute bounded real syncs and report exact observed outcomes separately from fixtures.
8. Update source/operations/security/schema docs, review changes, package source without credentials or live raw payloads, and stop at the Phase 2 gate.
