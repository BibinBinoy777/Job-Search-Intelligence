# Phase 3 final verification and completion

Verified 2026-10-28, Asia/Calcutta. **The local Phase 3 functional acceptance gate is met.** Independent recommendation-quality validation is outstanding and is not implied by this report. Phase 4, resume processing, notifications, external applications and production publication have not begun. No Git commit, push or remote-CI publication was performed.

## 1. Implemented capabilities

The deterministic engine analyzes recorded candidate professional evidence, normalizes conservative skill aliases, extracts required/preferred/incidental job mentions and exact supporting spans, compares skills/experience/role/location/preferences, and separates relevance, recognized eligibility constraints and evidence coverage. It stores versioned private results, detects changed inputs, supports bounded refresh and continuation, and exposes recommendations, pair explanations and status. The UI includes recommendations, an overview preview, component/evidence details, unknown/empty/stale/error states and existing save/application actions.

## 2. Genuine-job verification

The existing PostgreSQL database retains the same 80 genuine Himalayas job IDs and SHA-256 signatures of source description/title/source identity/status. No synthetic vacancy was inserted into that database. A clearly synthetic temporary private QA profile enabled a real HTTP/UI test without inventing the user's qualifications.

The fresh live refresh considered 80, calculated 80, failed 0 and completed. Its immediate repeat considered 80, calculated 0, reused 80, failed 0. There were 70 assessable scores and 10 null scores. All 80 structured analyses regenerated identically. All 80 complete stored assessment payloads replayed identically from their recorded candidate snapshot, source inputs and assessment time. All 203 extracted skill evidence spans matched source text; totals were 61 required, 13 preferred and 60 incidental skill classifications across jobs. This validates provenance and operation, not extraction correctness against human labels.

The source job count stayed 80; ingestion runs stayed 4 and ingestion records 160. Saved jobs, applications and application events were 0 before and after cleanup, so live-data preservation of nonempty tracking records is not claimed. The isolated migration test preserved representative save/application/event records, and browser tests exercised saves/tracking/reload. Only the two synthetic private Phase 3 QA accounts and their dependent private records were removed after checks. The 80 public requirement analyses remain cached. No original candidate or source records were removed.

A further read-only walk verified **all 269 extracted requirement evidence spans**, including experience, qualifications and unresolved conditions, against their cached source fields. This used validation Python with `../../../../work/verify_phase3_all_spans.py` from `apps/backend` and checked all 80 analyses.

Evidence: [live HTTP/UI counters](phase3-live-evidence.json), [integrity/replay/preservation](phase3-live-integrity.json), [migration](phase3-migration-evidence.json).

## 3. Scoring and reproducibility

Ranking identity is `evidence-baseline-1.0.1+d5546bafea1c`. Weights: required skills .40, preferred .10, experience .20, role .15, location preferences .10, other preferences .05. Score is the available-weight normalized mean × 100, rounded to two decimals. Null components stay unknown. Incomplete profiles and missing descriptions do not receive fabricated scores. Scores are not hiring probabilities. See [methodology](matching-methodology.md) for precise component/coverage definitions and limitations.

Stable ordering uses current before stale, assessable before null, descending relevance, then job UUID. Fingerprints cover candidate child records, job requirements/availability/source identity, ranking manifest and UTC assessment day. Tests cover skill addition/deletion, experience and education edits/deletes/reverts, preference changes, job changes, configuration changes and assessment-day changes. A prior candidate fingerprint is reusable only with the same current job/configuration/date tuple; a changed job still invalidates it. Repeats retain original assessment IDs/timestamps rather than duplicate rows.

The final review corrected misleading incomplete-profile help text: a target role alone is insufficient; recorded skills/experience/projects are needed. The ranking base version was bumped so previous explanation payloads are not falsely claimed to be outputs of the changed version. Additional invalidation tests were added without weakening existing assertions.

## 4. Database and migrations

The additive `0003_matching` migration adds nullable voluntary current country, public requirement-analysis cache, private match results and private refresh history, with foreign keys, unique input/version identities and score/coverage bounds. Existing tables remain intact. The already executed 0002-to-0003 upgrade check used an isolated `_test` database and retained nine representative user/profile/source/job/save/application/event/ingestion records, including application note/history and source fingerprint. Current `alembic check` found no pending metadata operations. Request transactions commit before returning success; unexpected database failure rolls back the request, and known per-job invalidity can produce an explicitly partial run.

## 5. Exact regression commands and results

Commands below use `python` for the actual validation interpreter `C:\Users\pc\Documents\Codex\2026-10-27\wwe\work\venv\Scripts\python.exe`. Backend commands run in `apps/backend`; frontend commands in `apps/frontend`; launcher runs at project root. The separate audit interpreter was `../../work/audit-venv/Scripts/python.exe` relative to project root.

| Check | Executed command | Result |
|---|---|---|
| Backend full suite | `python -u -m pytest -q` | **108 passed in 49.44s**, actual migrated PostgreSQL |
| Backend lint | `python -m ruff check .` | All checks passed |
| Backend format | `python -m ruff format --check .` | 55 files already formatted |
| Migration/schema | `python -m alembic check` | No new upgrade operations detected |
| Python dependency compatibility | `python -m pip check` | No broken requirements |
| Frontend components | `npm.cmd test` | **19 passed, 3 files**, 30.30s |
| TypeScript and production build | `npm.cmd run build` (`tsc -b && vite build`) | Passed; 1,648 modules; JS 390.40 kB / gzip 117.31, CSS 32.82 kB / gzip 7.79 |
| Frontend format | `npx.cmd prettier --check src e2e live-e2e` | Passed after formatting two browser files |
| Isolated browser workflows | `.\scripts\browser-tests.ps1 -Python 'C:\Users\pc\Documents\Codex\2026-10-27\wwe\work\venv\Scripts\python.exe'` | **3 passed in 27.1s**, real Chromium/HTTP/PostgreSQL |
| Genuine-job browser workflow | `npx.cmd playwright test phase3.spec.ts --config playwright.live.config.ts` | **1 passed in 6.0s**, no page errors |
| Offline rubric | `python -m app.modules.matching.evaluation --output ../../docs/matching-evaluation-results.json` | Executed successfully; limitations below |
| npm vulnerability audit | `npm.cmd audit --json` | 206 dependencies; 0 reported vulnerabilities |
| Python vulnerability audit | Audit Python: `-m pip_audit -r requirements.lock.txt --no-deps --disable-pip --format json --output ../../../../work/python-audit-phase3.json` | 44 pinned packages; 0 reported vulnerabilities; 0 skipped |

No ESLint task is configured; frontend checks are TypeScript, tests and Prettier. Production builds are local, not deployments. Dependency findings reflect the execution date, not a security certification. Initial post-resume DB checks could not connect because PostgreSQL was stopped; the existing cluster was restarted without resetting data, blocked command processes were stopped, and final runs above completed successfully. An Alembic invocation from project root failed for missing config; the correct `apps/backend` invocation passed. These environment/command retries were not product defects.

The live integrity verification was executed with validation Python and `../../../../work/verify_phase3_live.py` from `apps/backend`. It asserted analysis and full assessment replay, source span equality, unchanged job signatures/counts and exact-email QA cleanup in one transaction. The earlier isolated upgrade command was validation Python with `../../../../work/verify_phase3_upgrade.py`. These operator scratch scripts are outside the portable source package; persisted aggregate results are linked above. No secrets are included.

## 6. Frontend/browser review

The isolated browser suite covers profile/preferences, search, saving, application/history/reload, authorization, match refresh, repeat reuse, evidence, skill invalidation, stale opt-in and recalculation. Component tests cover not-calculated/null, missing profile, refresh failure, partial completion and unavailable pair states. The genuine-job run confirms source-attributed listings and actual server assessments in the UI. Five Phase 3 screenshots were visually reviewed across desktop, mobile and explanation layouts: readable cards/filters, no observed clipping, separate relevance/coverage/eligibility and exact evidence. This is Chromium coverage, not a claim of exhaustive cross-browser or assistive-technology validation.

Images: [genuine recommendations](phase3-live-recommended.png), [genuine-job assessment](phase3-live-analysis.png), [isolated desktop](phase3-recommended.png), [isolated mobile](phase3-recommended-mobile.png), [isolated evidence](phase3-matching-explanation.png). Synthetic browser fixtures are visibly marked TEST ONLY. The genuine QA screenshot's 100/100 score has only 30% applicable scoring weight and no measurable requirements; it is an explicit illustration of the normalization limitation, not a candidate endorsement.

## 7. Security and failures

Backend tests confirm authentication on refresh/status/list/pair, session-derived ownership, cross-candidate isolation, rejected client candidate IDs, bounded refresh size and filters, safe SQL-error responses, request rollback, per-job partial failure and concurrent refresh idempotency. Candidate evidence remains private and absent from global job responses. Existing Phase 1/2 security tests still pass. A complete result is never returned for a rolled-back request. [Security evidence](phase3-security-evidence.json) records dependency findings and checks.

## 8. Evaluation and outstanding limitations

The 3-candidate/16-job/4-query rubric is synthetic, agent-authored, not independently reviewed and not training data. Macro Precision@K .75, Recall@K 1.0 and NDCG@K 1.0 are specification diagnostics only. The title-only comparator is .375/.5/.759471 on the same admitted pool. No real-world accuracy or unbiased superiority is established. See [full evaluation methodology](matching-evaluation.md).

Known limitations: narrow aliases/role vocabulary, heuristic requirement extraction, incomplete/scoped years interpretation, conservative alternative-skill handling, ongoing employment not credited as completed duration, unresolved degrees/authorization/timezones, limited salary comparison, no coverage penalty/calibration, no independent labels/outcomes, historical snapshot retention without automated pruning, in-memory list/status evaluation and no distributed refresh quotas. These are disclosed baseline/production limits. No outstanding failing functional check is known; independent ranking-quality validation, large-scale behavior and production security readiness remain unverified.

## 9. Final source review and acceptance

This directory has no Git checkout. Final review uses SHA-256 inventory against the retained Phase 2 ZIP manifest, with every changed/added path listed in `phase3-file-review.json`. Prior Phase 1/2 ZIPs are preserved. The Phase 3 source ZIP includes source/tests/migrations/docs/evaluation fixtures/screenshots and `SOURCE_MANIFEST.sha256`. Runtime databases, private `.env`, credentials, virtual environments, dependencies, generated builds, logs and browser traces are excluded. Archive CRC, source hashes and a known-private-credential scan are checked during packaging.

Final inventory: 37 added paths, 18 changed paths and no removed paths versus Phase 2, plus the generated review/manifest. The ZIP contains 132 files. Changed historical QA PNGs were regenerated by the retained browser workflows. Final readiness and frontend HTTP checks returned 200; unauthenticated matching list/status checks returned 401. Archive CRC, all manifest hashes and the known-private-credential scan passed.

The functional acceptance criteria are met by real-job operation, exact replay/versioning, source-grounded explanations, honest unknowns, invalidation/security tests, intact prior workflows, passing final regression/build and completed documentation. **Phase 3 is complete as a local deterministic baseline; independent ranking validation and production readiness remain future work.**
