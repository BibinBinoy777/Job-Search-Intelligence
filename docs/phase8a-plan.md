# Phase 8A implementation plan

Extend the existing modular monolith. Preserve all original values via original-column hashes and all 100 job IDs. No source refresh, public deployment, Git commit/push or Phase 8B work.

1. Implement native PostgreSQL snapshot backup, referenced private-document inventory, integrity validation and isolated restore with measured timing. Exercise missing/tampered files and populated candidate metadata in isolated databases.
2. Add controlled Windows startup/shutdown and a supervisor around the existing worker, persistent health, restart/backoff and real process interruption tests.
3. Add secure recovery/session controls and owned export/deletion with a recoverable deletion state; additive migration and private cleanup tests.
4. Sanitize parser environment, isolated temporary working directory and explicit resource/network boundary; retain existing limits and truthful unconfigured scanning state.
5. Extend safe health/operations UI and structured logging, validate configuration and operational retention.
6. Run migration/preservation, backend/frontend/browser/build/security checks and document measured local capabilities versus remaining Phase 8B obligations.

Baseline: Windows 11, Python 3.12.14, Node installed, portable PostgreSQL 18.4, schema 0006_automation. Actual database: 100 jobs, 5 runs, 180 ingestion records, 20 job events/tasks, 80 requirement analyses, zero candidates/resumes/notifications. Private document root does not yet exist. No cryptography Python package present. Existing session auth, ingestion locks, leases, outbox and parser process are reused. Local cluster startup recovered the existing cluster without reseeding or migration.
