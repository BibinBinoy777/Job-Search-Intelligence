# Phase 5 completion and verification

Verification date: 28 October 2026, Asia/Kolkata. This completes the existing implementation in place. No database reset, Git publication or Phase 6 work was performed.

## Implemented functionality

The resume page is connected to the existing authenticated navigation. Candidates can upload PDF/DOCX files, inspect a private library with filenames/dates/versions/states, upload immutable revisions, download owned attachments, extract selected versions, inspect structured proposals and exact evidence, edit/accept/reject/leave pending/request clarification, preview conflicts and explicitly confirm selected accepted changes. The result reports actual actions, unresolved items and whether matching inputs changed. Deletion requires a second action and supports pending-cleanup retries. Upload/processing failures remain visible; busy labels do not pretend to measure percentage progress.

Files created/modified are enumerated by the final [source inventory and working-tree review](phase5-file-review.json); [SOURCE_MANIFEST.sha256](../SOURCE_MANIFEST.sha256) covers the packaged source. Main additions are `apps/backend/app/modules/resumes/`, `app/api/resumes.py`, the resume migration, `tests/test_resumes.py`, synthetic fixture generators/documents, `apps/frontend/src/features/resumes/`, component/browser tests and the resume documentation. Existing models/schemas/candidate services/session cleanup, routing/styles, dependencies, browser-test storage isolation and README are extended. Prior Phase 1–4 archives remain available and historical screenshots are preserved. This directory is not a Git checkout, so final review uses SHA-256 comparisons with the Phase 4 source archive rather than inventing Git status.

## Data model, storage and parsing

Additive migration `0005_resumes` creates resumes, resume_versions, resume_extractions, resume_proposals and resume_confirmations, with ownership FKs, cascading document cleanup and uniqueness for versions/proposals/processing reuse/idempotency. Existing experience gains nullable current-role status; education gains unknown completion by default. The [populated upgrade check](phase5-migration-evidence.json) preserved every original column value across 14 representative non-empty tables, including profile history, saved searches, application events/notes, ingestion, analyses and private matches. Alembic schema comparison passes.

Supported formats are PDF and DOCX; default upload limit is 5 MiB, private quota 50 MiB, 10 documents and 20 versions each. Backend streamed-size, extension/MIME/signature and structural validation are enforced. Files live under a configurable private filesystem root, outside frontend/static roots, addressed by random UUIDs with no internal storage path/reference in public response models. Authenticated downloads never grant public URLs. No real malware scanner is configured or executed.

pypdf extracts page-bounded text; bounded ZIP plus defusedxml extracts supported DOCX paragraphs/tables/headers/footers without invented page numbers. Child processes enforce 512 MiB memory and a 15 second timeout; two parser children per API process. Text, page, segment, proposal and archive expansion limits fail safely. Image-only PDFs report missing text/OCR requirement where detected; no OCR or external AI was performed. Exact ISO dates are retained; partial dates, ambiguous completion, absent achievements and certification validity remain unknown/unverified. See [extraction limitations](resume-extraction.md) and [security/storage operations](resume-security.md).

## Evidence, review, confirmation and matching

Both actual parsers were exercised on isolated synthetic documents. Tests verify PDF pages, DOCX table paragraphs and each qualification's exact `segment.text[start:end]` excerpt, version and method. Seven supported proposal categories are covered: skills, experience, education, summary, certifications, projects and languages. Incidental/negated skill mentions and negated education completion have dedicated checks. Source proposals/evidence stay immutable; candidate corrections are separately labeled values.

Upload, processing and decisions leave the authoritative profile untouched. Accepted items apply only through explicit selected confirmation; rejected and pending items remain unapplied. Canonical skill duplicates are no-ops. Conflicting employment/education require a deliberate separate-record/skip decision; existing summary requires explicit replacement. Existing manual records are not silently overwritten. Confirmation history persists selected actions and target references alongside immutable proposal/review values until document deletion.

Tests verify stale profile/review fingerprints return 409, identical confirmation-key retries return the same committed result, key reuse with different choices fails, and two concurrent identical confirmations serialize to one profile write. An injected failure on the second skill update rolls back the first write, every applied marker, revision and history; retry succeeds. A lost-response retry does not create duplicate qualifications. Confirmations for every supported category change existing matching inputs when appropriate; skill deduplication does not.

Existing Phase 3 engine/configuration/requirement-extractor hashes are unchanged. Matching input fingerprints detect confirmed changes, preserve stored assessments and mark them stale; no extraction/review/rejection triggers a fabricated recalculation. Another candidate's assessments remain unchanged. The existing explicit refresh mechanism remains the only recalculation path. No measured extraction-accuracy or recommendation-quality improvement is claimed.

## Deletion, authorization and failure recovery

Ownership tests exercise metadata, downloads, processing, extraction lists/evidence, preview, review, confirmation, version uploads and deletion across candidates. Unowned IDs return 404; anonymous access fails; IDs/request bodies are validated. Invalid extensions, MIME/signatures, malformed PDF/DOCX, empty files, backend oversize including streamed input, password-protected PDF, active/unsafe archives and external XML/relationships are rejected safely. Structurally valid blank/no-text documents can upload but extraction records a safe failure; no extracted facts or success are fabricated. Character/page/section bounds and parser timeout/retry are tested.

Upload commit failures clean newly written bytes. Filesystem deletion failures retain a durable tombstone and return 202; retry deletes all original versions and cascades extraction text/proposals/evidence/history. An injected failure after bytes are removed but before final DB commit retains the tombstone and recovers on retry. Confirmed profile information survives deletion. Generic audit events retain action/resource UUID/user/time only, without document text. Parser documents use memory rather than temporary files. Normal private-file cleanup is verified; crash-orphan reconciliation and backup retention remain operator responsibilities described in [retention/recovery](resume-security.md#retention-and-recovery).

## Final verification commands and results

Commands run from `apps/backend` with the existing validation venv; frontend commands from `apps/frontend`. Integration fixtures guard the database suffix `_test`; browser fixtures guard `_browser`. Neither resets development data.

| Check | Command / method | Final result |
|---|---|---|
| Complete backend regression | `python -m pytest -q --tb=short` | 187 passed, 0 failed, 0 skipped: 143 existing + 44 resume tests |
| Resume targeted verification | `python -m pytest tests/test_resumes.py -q --tb=short` | 44 passed, 0 failed, 0 skipped |
| Frontend component regression | `npm test` | 36 passed in 5 files; 0 failed/skipped |
| Chromium + real HTTP/PostgreSQL | `scripts/browser-tests.ps1 -Python <venv-python>` | 6 passed: 4 existing workflows + PDF and DOCX review flows; 0 failed/skipped |
| TypeScript | `npm exec tsc -- -b --pretty false` | Passed |
| Production build | `npm run build` (`tsc -b && vite build`) | Passed |
| Backend lint / format | `python -m ruff check app tests migrations`; `python -m ruff format --check app tests migrations` | Passed; 77 files formatted |
| Frontend format | `npm exec prettier -- --check src e2e` | Passed |
| Dependency consistency | `python -m pip check` | No broken requirements |
| Python advisory audit | `pip_audit -r requirements.lock.txt --no-deps --disable-pip --format json` | 46 pinned packages; 0 known vulnerabilities; 0 skipped |
| npm advisory audit | `npm audit --json` | 0 known vulnerabilities |
| Database migration/schema | Populated disposable 0004→0005 upgrade and `python -m alembic check` | Passed, no drift |
| Development preservation | Original-column full-row SHA-256 + count check for all 21 original tables | Passed |
| Source package review | Previous archive comparison, CRC, manifest hashes and known credential scan | Passed; runtime/private files excluded |
| Running local app | Readiness and frontend HTTP checks, anonymous private-read checks | Ready; private routes require authentication |

Earlier iterations exposed new-test assumptions about timezone-equivalent timestamps, an existing skill API's 200 response and the required refresh JSON body; those expectations were corrected. A component upload test uses an explicit submit event because jsdom's native file-required validity does not model Chromium's behavior; both real Chromium file-upload/submit flows pass. Initial newly added test failures were resolved; existing Phase 1–4 tests were retained. The final results above refer to the successful final runs. PostgreSQL had stopped between sessions; the same cluster was restarted and recovered, without reinitialization or record replacement. The legacy live browser suite was deliberately not run because it creates synthetic development candidates, prohibited for this Phase 5 QA.

The [development preservation evidence](phase5-preservation-evidence.json) independently confirms all 80 genuine jobs, 160 ingestion records, four ingestion runs, 80 cached analyses, one source, 32 existing audit events and every original value are retained. Candidate-related development tables were empty at baseline and remain empty; no synthetic Phase 5 resume/candidate/job records were added there. Non-empty candidate/profile/save/application/match preservation is independently exercised by the disposable populated migration fixture. No freshness claims were renewed for old vacancies.

See [structured security/test evidence](phase5-security-evidence.json), [PDF browser screenshot](phase5-pdf-review.png) and [DOCX browser screenshot](phase5-docx-review.png). Screenshots contain explicitly synthetic isolated QA data, not a real candidate's qualifications.

## Acceptance and remaining production limitations

Phase 5 meets its local functional acceptance criteria: supported uploads, rejection/security/ownership, actual parsers and traceable proposals, candidate-controlled decisions/confirmation, conflict/concurrency/rollback safety, existing matching invalidation, recoverable deletion, preserved earlier behavior/data, passing checks and aligned documentation. No local acceptance blocker remains after the successful final checks.

Production deployment is not certified. Remaining limitations include no OCR, external AI or real malware scanner; heuristic parsing rather than independently evaluated extraction accuracy; local filesystem storage rather than managed encrypted object storage; Windows ACLs/TLS/backup retention to configure; no automatic orphan sweeper for hard process crashes; and parser subprocess bounds without a full filesystem/network sandbox. Shared rate limiting, account recovery, operational monitoring and independent security/extraction-quality review remain deployment work. They are not presented as completed integrations. No Phase 6 feature, automatic application submission, notification workflow, Git commit/push/branch publication or remote CI publication was started.
