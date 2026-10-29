# Phase 5 plan

Inspected Phase 4 source manifest (all hashes matched), existing profile/services/session/error handling, matching snapshots, migrations, frontend and tests. Live baseline: 80 genuine jobs, 80 cached requirement analyses, four ingestion runs, 160 ledger rows; no candidate profiles/private matches/resumes. No live synthetic candidates or resumes will be created for this phase.

1. Add private versioned resumes, bounded extraction runs/proposals and confirmation provenance through additive migration. Reuse existing profile models; add explicit unknown completion/current-role metadata where needed.
2. Raw authenticated bounded upload (PDF/DOCX), random internal paths outside web roots, signature/structure validation and authorized attachment download. Compensate filesystem writes on transaction rollback; retryable deletion tombstones protect DB/file consistency.
3. Separate parser process with wall-clock/memory/content limits. pypdf for PDF, bounded ZIP + defusedxml for DOCX paragraphs/tables/headings. No OCR, external AI or malware-scanning claim.
4. Conservative section/delimiter/date/skill extraction with exact immutable segment offsets. Unsupported facts stay unknown and proposals remain separate from profiles.
5. Revision-checked review, preview of duplicates/conflicts and explicit selected confirmation through existing candidate services. Append/preserve by default; explicit conflict choices; transaction/idempotency protection. Reuse matching fingerprint invalidation without changing ranker.
6. Resume library/review UI, isolated synthetic PDF/DOCX fixtures, security/failure/rollback/deletion/browser/regression and migration/preservation evidence; documentation and Phase 5 source package. Stop before Phase 6.
