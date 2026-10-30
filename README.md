# Job Search Intelligence

Phases 1–7 are locally verified; Phase 8A results are recorded in docs/phase8a-validation.md. This repository contains source, migrations and explicitly synthetic test fixtures. It excludes the local runtime database, candidate records, uploaded resumes and credentials, and is not a production deployment. Fresh installations start empty; collect jobs using the documented authorized ingestion workflow. Reported job counts and eligibility are dated local observations.

A personal career workspace for profiles, genuine jobs, evidence-based recommendations, saves and application progress. Phase 7 extends the existing modular monolith: React/TypeScript/Vite frontend, Python/FastAPI services, SQLAlchemy and PostgreSQL, with Alembic migrations.

A fresh database starts empty. Phase 2 integrates the permitted Himalayas API: durable ingestion runs, cursor pages, canonical normalization, safe source identity updates, availability verification, source health and operator controls. The existing development database now contains 100 genuine collected listings from bounded live verification. Phase 3 adds private versioned deterministic relevance assessments, separate eligibility and evidence coverage, exact source evidence and recommendations. Missing information remains unknown; scores are not hiring probabilities. Phase 5 adds private PDF/DOCX versions, bounded local extraction, source-backed qualification proposals, candidate review and explicit transactional confirmation. Phase 7 adds opt-in alerts, durable events/tasks/outbox, in-app delivery, optional SMTP and explicit timezone-aware reminders. External application submission remains unimplemented. Synthetic test vacancies stay in disposable databases, and the offline rubric dataset is explicitly synthetic.

See the [Phase 7 completion report](docs/phase7-validation.md), [automation architecture and recovery](docs/automation-architecture.md), [alert semantics](docs/job-alerts.md), [notifications and email](docs/notifications.md), [application reminders](docs/application-reminders.md), and the historical [Phase 6 completion report](docs/phase6-validation.md), [career architecture and interpretation](docs/career-intelligence.md), and the historical [Phase 5 completion report](docs/phase5-validation.md), [resume architecture](docs/resume-architecture.md), [extraction and evidence](docs/resume-extraction.md), [private storage and retention](docs/resume-security.md), and the historical [Phase 4 completion report](docs/phase4-validation.md), [search architecture](docs/search-architecture.md), [comparison and saved searches](docs/job-comparison.md), [search evaluation](docs/search-evaluation.md), and the historical [Phase 3 completion report](docs/phase3-validation.md), [matching architecture](docs/matching-architecture.md), [methodology](docs/matching-methodology.md) and [evaluation limitations](docs/matching-evaluation.md).

## Layout

```text
apps/backend/app/
  api/                    HTTP routes, schemas and authenticated dependencies
  core/                   Configuration, password/session security, logging
  db/                     SQLAlchemy models, sessions and repositories
  services/               Candidate, job, authentication and application rules
  modules/sources/        Typed Himalayas adapter, normalization and safe HTTP transport
  modules/matching/       Versioned extraction, evidence, eligibility, scoring and refresh
  modules/search/         Database lexical retrieval, current matching context and evaluation
  modules/resumes/        Private versions, bounded parsing, evidence, review and confirmation
  modules/career/         Read-only skill gaps, roles, paths, learning and sample evidence
  ingestion/              Run control, persistence, freshness, worker and operator CLI
apps/backend/migrations/  Explicit, versioned schema changes
apps/backend/tests/       PostgreSQL integration tests and browser-only fixtures
apps/frontend/src/
  app/                    App shell, routing and responsive styles
  features/               Overview, profile, discovery, saved jobs, applications, settings
  components/             Accessible shared fields, states and pagination
  services/               Cookie-authenticated API client
  types/                  API response interfaces
  tests/                  Component tests with explicitly mocked HTTP
apps/frontend/e2e/        Real Chromium + HTTP + PostgreSQL workflows
docs/                     Architecture, schema, API, security and validation evidence
scripts/                  Browser-test launcher
```

## Prerequisites

- Python 3.12+, Node 22.12+ (or 24+) and npm.
- PostgreSQL 16+ (validation used actual PostgreSQL 18 portable binaries).
- A modern browser. No Docker or external auth/AI credentials are required.

On Windows, use the official [PostgreSQL installer](https://www.postgresql.org/download/windows/) or your existing PostgreSQL server. Start its service, create a dedicated non-superuser application login and databases using pgAdmin or `psql`. The commands below run in PowerShell, from this project root.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r apps\backend\requirements.lock.txt
Copy-Item .env.example .env
```

Replace `.env` placeholders with your own URL-encoded credentials and database names. Never commit `.env`. Example database names are `job_search`, `job_search_test` and `job_search_browser`; the test databases must be separate and disposable. Use pgAdmin to create the login/databases, or run these commands as a local PostgreSQL administrator in `psql` (replace the password placeholder):

```sql
CREATE ROLE job_search_app LOGIN PASSWORD '<replace-with-a-long-random-password>';
CREATE DATABASE job_search OWNER job_search_app;
CREATE DATABASE job_search_test OWNER job_search_app;
CREATE DATABASE job_search_browser OWNER job_search_app;
```

Set `DATABASE_URL=postgresql+psycopg://<user>:<password>@127.0.0.1:5432/job_search` in `.env`. Set `TEST_DATABASE_URL` and `BROWSER_DATABASE_URL` to their own databases. Never direct tests at development or production records: the guarded fixture scripts truncate their target databases.

## Migrate and run

Terminal 1, from the project root:

```powershell
Set-Location apps\backend
..\..\.venv\Scripts\python.exe -m alembic upgrade head
..\..\.venv\Scripts\python.exe -m alembic check
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Terminal 2, from the project root:

```powershell
Set-Location apps\frontend
npm.cmd ci
npm.cmd run dev -- --port 5173 --strictPort
```

Open `http://127.0.0.1:5173`, choose **Create an account**, and use a password of 12Ã¢â‚¬“128 characters. Registration signs you in; create your candidate profile before saving jobs or tracking applications. There are no built-in user accounts or privileged passwords. The frontend proxies `/api` to port 8000; sessions use an HttpOnly cookie. API docs are at `http://127.0.0.1:8000/docs`.

For Linux/macOS, use `python3 -m venv .venv`, `.venv/bin/python`, and `npm`; all backend paths and migrations are otherwise unchanged.

### Existing validation environment on this machine

The app was launched at `http://127.0.0.1:5173` with the API on port 8000. A private `.env` already configures PostgreSQL on `127.0.0.1:55432`. Runtime files live in `../../work/`, relative to this project root, and are not part of the source deliverable. If those processes have stopped, restart PostgreSQL using the portable `pg_ctl.exe` under `../../work/postgres/node_modules/@embedded-postgres/windows-x64/native/bin`, data directory `../../work/pgdata`, and log `../../work/postgres.log`. Do not delete that data directory to troubleshoot.

Use `../../work/venv/Scripts/python.exe` instead of `.venv/Scripts/python.exe` for the existing validation virtual environment. Follow the prerequisite steps above for a clean, portable installation. PostgreSQL stores actual application data on disk; source files alone do not contain candidate records.

## Phase 2: collect genuine listings

From `apps/backend`, using your virtual environment's Python:

```powershell
python -m app.ingestion.cli configure --page-limit 2
python -m app.ingestion.cli sync --source-id <the-source-uuid-printed-above>
```

Replace the UUID placeholder with the actual configure output. This explicitly performs a bounded live API sync (up to 40 records), verifies availability and persists results. It prints real run counters; `limited` means more provider pages remain. Use **Discover jobs** for collected records and **Data sources** for actual health, last attempt/success, page limits, record diagnostics and run reconciliation. Country/timezone restrictions remain visible; remote does not imply worldwide eligibility.

For queued operator requests, keep a separate `python -m app.ingestion.cli worker` process running. An existing account can be explicitly promoted by a trusted local operator using `python -m app.ingestion.cli promote --email <existing-email>`. Accounts default to ordinary candidates. Only operator accounts see queue/resume controls; the API independently checks the role. HTTP sync returns 202 with a run ID and needs a worker; queued is not success.

Scheduling is optional and disabled by default. To opt into daily sync, use `configure --page-limit 2 --schedule-hours 24` and `worker --schedule`. Public Himalayas access needs no API key. Optional `HIMALAYAS_API_KEY` stays server-side. `INGESTION_TIMEOUT_SECONDS`, `INGESTION_MAX_BYTES`, and `INGESTION_ATTEMPTS` have bounded defaults.

Original links retain the API's application URL, and each Himalayas card/detail includes credit. [Official API documentation](https://himalayas.app/docs/remote-jobs-api) and [API terms](https://himalayas.app/terms) govern use; this app does not syndicate records to external boards or submit applications. See [source assessment](docs/data-sources.md) and [operator commands/recovery](docs/ingestion.md).

Integrated jobs require recent availability evidence and disappear from discovery after a source deadline or the 24-hour verification window. This is distinct from declaring them source-confirmed closed. Manual imports preserve the Phase 1 workflow and cannot overwrite an installed network adapter's records.

## Phase 6: Career Intelligence

Open **Career intelligence** with an existing profile. The dashboard connects your recorded skills to potential gaps, roles to explore, inferred career paths, skill-specific learning actions and sample-based market evidence. A resume is optional. Unconfirmed resume suggestions remain separate and link back to review; this page never confirms qualifications or recalculates matching assessments.

Choose a target role, source UUID, literal listing location, publication range or required/preferred skills. Target-role defaults reuse saved preferences; without a saved target the initial population uses recorded skill overlap. Every statistic shows a denominator, supporting jobs, exact public requirement excerpts and data limits. Role discovery uses the broader scoped sample; selecting **Use as target** recalculates target gaps and learning. Change saved target roles through Settings. No title-only suitability, hiring odds, salary improvements or standard transition timelines are claimed.

Checked provider documentation links show their verification date and evidence; unchecked learning directions have no invented course/provider/URL. Resource verification is a dated snapshot, not a live guarantee. Current genuine stored listings can be excluded by freshness rules; when no eligible sample remains the dashboard shows that honestly. Reverify listings using the existing authorized ingestion workflow before relying on current market observations; Career Intelligence does not relabel old records as fresh.

No migration, package or configuration addition is required; database head remains `0005_resumes`. The complete backend and browser commands below include Phases 1–6. Targeted backend tests: `python -m pytest tests/test_career.py -q`. See [career methodology, privacy, limits and API](docs/career-intelligence.md) and [actual completion evidence](docs/phase6-validation.md). All synthetic career QA stays in `_test`/`_browser` databases.

## Phase 5: private resume intelligence

Open **Resume intelligence** after creating a profile. Upload a PDF or DOCX (5 MiB maximum by default), extract its selected version and inspect each proposal's exact source span. Accept, edit, reject, leave pending or flag clarification. These actions alone never update your profile. The preview lists duplicates/conflicts; select accepted items, choose conflict resolutions explicitly and press **Confirm selected changes**. Only committed changes are reported applied. Relevant prior assessments become stale and need the existing deliberate recommendation refresh.

Versions are immutable; uploading an identical file creates a distinct version. Downloads require your session. Delete uses a second confirmation and preserves previously confirmed profile facts. A 202 deletion-pending response requires retrying deletion to finish cleanup. No OCR, external AI or malware scanning is configured/performed. Default storage is `~/.job-search-intelligence/private-resumes`; configure `RESUME_STORAGE_ROOT` outside every public web root, with private production ACLs/encryption. Files are excluded from source packaging. Parsing limitations, bounded resources, states and recovery are documented in [resume architecture](docs/resume-architecture.md), [extraction](docs/resume-extraction.md) and [security/retention](docs/resume-security.md).

From `apps/backend`, run `python -m pytest tests/test_resumes.py -q` for the resume integration/security tests or `python -m pytest -q` for all phases. Tests require the separate `_test` database. `scripts/browser-tests.ps1` uses only `_browser`, synthetic PDFs/DOCX under `tests/fixtures/resumes`, and a separate private `.local/browser-resumes` root. Do not run legacy live-browser tests for resume QA: they create temporary synthetic development profiles. No Phase 5 synthetic candidate or job is created in the real development database.

## Phase 4: search, compare and save definitions

Open **Discover jobs**. Enter keywords, location and optional employment/work-mode/source filters, choose **Sort by**, then **Search jobs**. Keyword terms combine with AND across supported public text fields; exact/strong title matches get a transparent lexical boost. Text relevance is distinct from candidate relevance and eligibility. Use **More filters** for title/employer, exact source country/region, known experience ranges, status/availability, actual dates, compatible salary units and current matching evidence. Active chips remove criteria. Reset clears the search; filters/sort reset the page. The URL supports refresh and back navigation.

Salary thresholds need both currency and period; unknown/incomparable values are excluded. Date filters use ISO timestamps with a timezone. Missing publication is never replaced with source modification time. Candidate score/coverage/eligibility filters use current stored assessments only; create/update your actual profile and explicitly refresh recommendations first. Missing and stale scores do not count as zero. Detailed evidence remains in job details. Matching quality is independently unvalidated.

The database retains 80 genuine listings. Availability changes with time: the final check saw 40 current listings and 40 requiring renewed source evidence. Use **Listing availability Ã¢â€ ’ All** deliberately to inspect historical identity/status; expired/unverified integrated content and application links stay suppressed. Search never resets timestamps, deletes old jobs or declares vacancies closed because a provider is unavailable. Source verification remains the existing operator workflow.

Select **Compare** on up to three cards/details and open **Compare selected jobs**. The table separates source facts from private assessments and supports remove/clear, original links, saves and the existing application tracker. Selection survives ordinary navigation; the comparison URL contains only public job IDs. On mobile the table scrolls horizontally within its labeled region.

Open **Saved searches**, give the applied definition a name, and save it. You can load, rename, replace criteria and delete your own definitions (up to 50). These are search conveniences: no automatic alerts or schedules. They store no copies of vacancies or private profile snapshots. A candidate profile is required to save searches.

Run the read-only genuine-record evaluation from `apps/backend`: `python -m app.modules.search.evaluation --output ../../docs/phase4-search-evaluation.json`. The report distinguishes specification correctness from human relevance validation. Standard backend/frontend/browser commands below include Phases 1–5.

## Phase 3: inspect recommendations

Create your profile and record actual skills, experience or projects, plus optional preferences. Choose **Recommended jobs**, then **Refresh recommendations**. Opening a screen does not calculate matches automatically. A batch assesses at most 200 available jobs; use continuation if more remain. Identical inputs reuse results. Profile/job/configuration changes and a new UTC assessment day mark old results stale. Previous assessments are opt-in and labeled; source freshness also applies.

Cards show relevance or an unassessable state, eligibility and coverage. **Inspect evidence** opens the component breakdown, required/preferred evidence and unresolved constraints. High scores can reflect a limited set of available components; inspect coverage and unknowns. Optional current country supports explicit source-country checks and does not establish work authorization. No resume or model credentials are required.

Ranking: `evidence-baseline-1.0.1+d5546bafea1c`. Live QA used explicitly synthetic temporary private profiles against genuine jobs; those accounts/results were removed after verification. No personal qualifications were invented for the real user. Sign in or create your own account to calculate personal recommendations.

## Tests

Backend, from `apps/backend`:

```powershell
..\..\.venv\Scripts\python.exe -m pytest -q
..\..\.venv\Scripts\python.exe -m ruff check .
..\..\.venv\Scripts\python.exe -m alembic check
```

Tests use `TEST_DATABASE_URL`, apply real Alembic migrations and compare schema metadata, truncate only the guarded `_test` database, authenticate real test users and issue actual FastAPI HTTP requests. No authorization bypass or in-memory SQLite replacement is used. Dependency failures are deliberately injected in the readiness/rollback tests; other database tests use real PostgreSQL.

Frontend, from `apps/frontend`:

```powershell
npm.cmd test
npm.cmd run build
npx.cmd playwright install chromium
```

Browser tests, from the project root, with ports 8001 and 5174 free:

```powershell
.\scripts\browser-tests.ps1 -Python "$PWD\.venv\Scripts\python.exe"
```

The script uses `BROWSER_DATABASE_URL` ending in `_browser`, migrates and resets that isolated database, adds two explicitly marked synthetic vacancies, starts temporary API/Vite servers, runs Chromium, and stops its servers. Alternatively, manually run `python -m tests.browser_data` from `apps/backend`, start the API with `DATABASE_URL` set to `BROWSER_DATABASE_URL` on port 8001, start Vite with `API_TARGET=http://127.0.0.1:8001` on port 5174, then run `npm.cmd run test:e2e` from `apps/frontend`. Include the browser origin in `ALLOWED_ORIGINS`.

See [current Phase 6 verification](docs/phase6-validation.md), [historical Phase 5 verification](docs/phase5-validation.md), [historical Phase 4 verification](docs/phase4-validation.md), [historical Phase 3 verification](docs/phase3-validation.md), [historical Phase 2 report](docs/phase2-validation.md) and [Phase 1 historical report](docs/validation.md) for executed results and [QA screenshots](docs/qa-overview.png) for synthetic browser-test data, not genuine vacancies.

The explicit `live-e2e/` tests use the running development app and genuine listings, outside normal isolated tests. Run `npx.cmd playwright test phase4.spec.ts --config playwright.live.config.ts` from `apps/frontend` only against this local development app. It creates a temporary QA account and records its email (no password) in `../../work/phase4-qa-accounts.json` relative to the project root for scoped cleanup. Do not run against production. Its separate output directory avoids artifact collisions. The report records the run and exact-account cleanup. `phase4-live-*.png` show genuine jobs with synthetic QA profiles; other Phase 4 images show isolated synthetic fixtures.

`qa-overview.png` / `qa-mobile.png` show synthetic isolated test data; `phase2-live-*.png` show actual persisted source records and their health.

## Importing actual supplied jobs

Phase 1 includes a trusted operator CLI so real, user-provided or permitted records can be stored without waiting for an integration. It does not fetch websites. From `apps/backend`:

```powershell
..\..\.venv\Scripts\python.exe -m app.cli C:\path\to\actual-jobs.json --source-name "Supplied employer records" --source-type manual
```

The JSON file is an array using the `JobIn` schema in `app/api/schemas.py`. Required keys are `title`, `employer` and `description`; provide only real details. Omit unknown fields, and use `status: "unknown"` unless status is evidenced. Source URLs must be HTTP(S), timestamps must include a timezone, and salaries require currency. Set `external_id` only when the original source supplies a stable identifier. The CLI assigns `source_id`; repeating the same source/external identity updates one record. Missing external IDs deliberately remain separate in Phase 1. Source integration stays disabled. No sample vacancies are shipped as real data.

## Build and production configuration

`npm.cmd run build` writes `apps/frontend/dist`. Vite's development proxy is **not** a production reverse proxy. Host those static assets behind HTTPS and route `/api` to the FastAPI service under the same origin. Run migrations as a deployment step; the API never creates tables at startup. Keep database ports private and use a least-privilege application role, independent backups and recovery tests.

Set `APP_ENV=production`, `COOKIE_SECURE=true`, explicit HTTPS `ALLOWED_ORIGINS`, a configured PostgreSQL URL, and choose `ALLOW_REGISTRATION` deliberately. Invalid production settings fail validation at startup. Local development cookies are intentionally non-Secure for localhost HTTP. Passwords use Argon2; session tokens are random, stored only as SHA-256 digests server-side, expire, and are revoked on logout.

Production rollout remains outside this local Phase 6 gate: shared rate limiting, verified email/account recovery, session/account management, TLS/proxy configuration, security review, monitoring, data export/deletion and tested backups remain required. The in-process authentication limiter is suitable only for a single local API process. External identity integration is behind the authenticated dependency boundary and can replace the local account service later. See [security](docs/security.md).

## Troubleshooting

- **Database unavailable / readiness 503:** check the PostgreSQL service, host/port, URL-encoded password, database existence and migration revision. Check `/api/v1/health/ready`. Liveness deliberately remains independent of the database.
- **No scored search results:** missing/stale/insufficient assessments cannot satisfy a score threshold. Refresh actual profile recommendations, inspect evidence, or remove that filter.
- **Invalid saved/search filter:** correct the displayed error; salary bounds need currency and period, date thresholds need timezone offsets, and only supported criteria are accepted.
- **Empty discovery:** expected on a new database. Check Data sources for actual run state; configure and run the installed adapter as documented below. Stale/closed integrated records are intentionally hidden.
- **401:** sign in. An expired or revoked session cannot authorize requests.
- **403 origin rejected:** use the configured frontend URL; add an exact trusted origin to `ALLOWED_ORIGINS` and restart the API.
- **409 while saving an application:** another request changed it. Refresh and retry against the current version. Duplicate tracking of the same job also returns 409.
- **422 changing an outcome:** offer/rejected/withdrawn can be corrected with a reason. Invalid dates, fields or missing expected version also return 422.
- **429:** the local auth limiter allows 12 attempts per client IP per five minutes per operation. Wait five minutes.
- **Port in use:** stop the relevant existing service or adjust both server and proxy/test settings consistently.
- **Chromium missing:** run `npx.cmd playwright install chromium` and wait for completion before testing.
- **Windows command not found:** use `npm.cmd` if PowerShell execution policy blocks `npm.ps1`; use the full Python executable path if `py` is unavailable.

## Next milestones

Phase 5 implements secure local resume intelligence with explicit candidate review. Independent real-world extraction/ranking-quality validation and production readiness remain outstanding. **Phase 6 adds read-only career intelligence; stop after local Phase 6 verification. Phase 7–8 are not implemented or started.**


## Phase 7 worker and notifications

Apply `0006_automation` using the normal `python -m alembic upgrade head` command in `apps/backend`. Run `python -m app.ingestion.cli worker --schedule` in a separate terminal. Ctrl+C stops that foreground worker. API startup does not start a worker. Keep PostgreSQL running. No unattended startup/supervisor is installed by this phase.

Source scheduling is off by default. Operators set the interval/page limit or pause a schedule in Data sources. The configured interval must be at least 24 hours. Manual source synchronization still queues the same existing pipeline. To configure a source locally: `python -m app.ingestion.cli configure --page-limit 1`; include `--schedule-hours 24` only when scheduling is intended. Operator promotion uses the existing `promote --email <registered-account>` CLI and does not bypass registration.

Candidates explicitly enable job alerts in Notifications, then create separate future-only subscriptions in Job alerts. A saved search alone does not subscribe. Missing/stale/insufficient match assessments never satisfy score conditions, and matching is not recalculated implicitly. Application reminders are explicitly scheduled from an owned application; existing follow-up dates do not auto-send. Digests, quiet hours and delivery guarantees are not implemented.

`AUTOMATION_ENABLED=true` enables downstream task/delivery processing. Source schedules have independent enablement. Optional SMTP requires `SMTP_HOST` and validated `SMTP_SENDER`; `SMTP_PORT=587` uses mandatory STARTTLS. `SMTP_USERNAME`/secret `SMTP_PASSWORD` are optional authentication settings. `APP_BASE_URL` defaults to `http://127.0.0.1:5173`; production SMTP requires an HTTPS origin. Without provider configuration, email stays unavailable and in-app still works. See `.env.example`; never place secrets in frontend variables.

Run the full backend tests with `python -m pytest -q` in `apps/backend`, frontend tests/build with `npm test` and `npm run build` in `apps/frontend`, and `scripts/browser-tests.ps1 -Python <python.exe>` from the root. Backend/browser fixture guards require separate `_test`/`_browser` databases. SMTP tests are mocks; no real email delivery is claimed. Review current results and live dataset eligibility in the dated Phase 7 report. Production supervision, HTTPS, backup/recovery validation and unattended monitoring remain Phase 8.


## Phase 8A local operations

See [startup/supervision](docs/local-operations.md), [backup/restore and DPAPI](docs/backup-recovery.md), [account security/export/deletion](docs/account-security.md), [file boundary](docs/file-security.md), [monitoring](docs/monitoring.md), and [deployment/migration preparation](docs/deployment-preparation.md). Account controls are at `/account`; sign-in includes local recovery confirmation. SMTP recovery delivery and malware scanning remain unconfigured.

Build the frontend, then use `scripts/start-local.ps1` with explicit Python/server-bin/existing-data-directory paths. Startup never resets or seeds data. Only explicit `-Migrate` applies migrations. `scripts/stop-local.ps1` drains application processes and leaves PostgreSQL running. Native backup/restore commands use `python -m app.operations.cli` from apps/backend, with an explicit PostgreSQL client-bin path and private backup destination. Source schedules remain opt-in.

Operational tests use the guarded disposable `_test` database. Set `JSI_PG_BIN` to a native PostgreSQL 18 client-bin directory before `python -m pytest -q` to execute actual backup/restore tests; without it those tool-dependent cases explicitly skip. DPAPI tests run only on Windows. Run `npm test -- --maxWorkers=1`, `npm run build` and the existing browser launcher for frontend checks. Dated exact results and restore measurements are in the Phase 8A report. No public hosting/domain, real email delivery or unattended production supervision is implied.
