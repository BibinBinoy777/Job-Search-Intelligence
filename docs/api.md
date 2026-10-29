# API reference

Interactive, generated contracts: `/docs`; JSON schema: `/openapi.json`. All application routes start with `/api/v1`. Credentials and other inputs are JSON. The API identifies the candidate with `jsi_session`, never a client user-ID header or parameter. There are no public candidate record lookup endpoints.

| Method | Path after /api/v1 | Behavior |
|---|---|---|
| POST | /auth/register | Register local password account; 201 and HttpOnly session cookie |
| POST | /auth/login | Verify password and start session |
| POST | /auth/logout | Revoke current session and clear cookie; 204 |
| GET | /auth/me | Authenticated user ID/email only |
| GET | /overview | Actual completion, save/application counts and recent activity |
| GET / POST / PATCH | /profile | Read, create (201), update current candidate profile |
| GET / POST | /profile/skills | Read/add normalized skills; adding same skill is idempotent |
| DELETE | /profile/skills/{id} | Remove an owned skill; 204 |
| GET / POST | /profile/experience | Read/add owned experience; create 201 |
| PUT / DELETE | /profile/experience/{id} | Replace/delete owned experience |
| GET / POST | /profile/education | Read/add owned education; create 201 |
| PUT / DELETE | /profile/education/{id} | Replace/delete owned education |
| GET / PATCH | /profile/preferences | Read/update career preferences |
| GET | /jobs | Search/filter actual canonical records |
| GET | /jobs/{id} | Details, source, freshness and candidate save flag |
| GET | /sources | Source metadata only; no integration is running |
| PUT / DELETE | /jobs/{id}/save | Idempotent owned save/removal |
| GET | /saved-jobs | Current candidate's saved job relationships |
| GET / POST | /applications | List/create current candidate's application; create 201 |
| GET / PATCH | /applications/{id} | Read/update owned application |
| GET | /applications/{id}/events | Read owned application history |
| GET | /health/live | Process liveness without DB dependency |
| GET | /health/ready | Database and migration readiness; 503 when unavailable |

`/jobs`, `/sources`, `/saved-jobs`, `/applications` and application event lists accept `page` (1+) and `page_size` (1Ã¢â‚¬“100, default 20). Responses contain `items`, `total`, `page`, and `page_size`; ordering includes a stable identifier where relevant. Profile child collections are returned as aggregate arrays, also embedded in `/profile` for editing.

Job filters: `q` (title, employer, description), `location`, `employment_type` (`full_time`, `part_time`, `contract`, `internship`, `temporary`), `work_arrangement` (`remote`, `hybrid`, `on_site`) and `source_id`. No fabricated relevance sorting or active-only assumption is applied. Current sorting is first-seen descending.

Profile PATCH fields distinguish omitted fields from explicit NULL scalar values. Preferences PATCH validates the merged stored object; salary requires currency. Skill inputs are exact normalized names, not unvalidated semantic aliases. Experience/education use complete PUT replacement with date validation.

Application creation requires a canonical `job_id`; optional fields include status, notes, actual `applied_on`, follow-up date, and an opaque future resume reference. Application PATCH requires `expected_version`, for example:

```json
{"expected_version": 1, "status": "applied", "notes": "Submitted manually", "applied_on": "2026-10-01"}
```

The response supplies the new version. Changing an outcome to another status requires `correction_reason`. There is no external apply endpoint.

Error envelope:

```json
{"error":{"code":"validation_error","message":"Check the highlighted fields","fields":[{"field":"body.status","message":"Invalid value"}]}}
```

401 means unauthenticated/expired, 403 rejected origin or disabled registration, 404 missing/unowned record, 409 duplicate or stale write, 422 invalid input/transition, 429 local authentication throttle, and 503 unavailable database/dependency. Raw SQL, DSNs, password values and exception traces are not returned. Mutations reject untrusted browser origins; CLI requests may omit Origin. Responses include a request correlation ID and no-store caching policy.


## Phase 2 extensions

Phase 1 routes remain. Authentication responses now include `is_operator` (false by default). Read-only source/run metadata contains no candidate details, credentials, raw cursors or provider payloads.

| Method | Path after /api/v1 | Behavior |
|---|---|---|
| GET | /sources/status or /ingestion/status | Source health, last run, stored/visible counts, queue capability and probable-duplicate count |
| GET | /ingestion/runs | Paginated history; optional source_id |
| GET | /ingestion/runs/{run_id} | Safe counters/progress, has_more and finished-run reconciliation |
| GET | /ingestion/runs/{run_id}/records | Paginated record outcomes/codes, no raw body or source identity hash |
| POST | /ingestion/sync | Operator-only JSON source_id and optional resume_run_id; 202 with durable queued run ID; separate worker required |

Source/run IDs are validated UUIDs. Candidates can inspect operational metadata but receive 403 for manual sync. Unauthenticated calls receive 401. Active source runs conflict with 409; a persisted rate-limit cooldown yields 429. Source management, recovery and role grants stay behind the trusted local CLI.

Jobs add `title`, `employer`, `status`, timezone-aware `published_after`/`updated_after`, salary bounds/currency/period and sort (`recent`, `title`, `published_desc`, `salary_desc`). Queries remain PostgreSQL substring searches with escaped wildcards; no semantic or full-text ranking is claimed. Salary range/salary sorting requires an explicit matching currency and period. Disclosed bounds are compared without exchange conversion or annualization; unknown pay periods cannot silently match an annual range.

Integrated jobs must satisfy the documented availability window to appear in discovery, even when a closed/expired status filter is requested. Manual/legacy records retain Phase 1 visibility. Job responses add source modification/deadline, status basis, location/timezone restrictions, categories, availability assessment and is_available. Unavailable/stale details remove vacancy content and apply links while preserving a private tracking reference. Publication remains NULL when the provider supplies only modification time.

Finished-run `reconciled` compares the durable record ledger with counters; it is NULL while queued/running so a moving checkpoint is not misreported as a broken invariant.


## Phase 3 matching endpoints

All endpoints require a verified session and resolve only that user's candidate. No candidate/profile ID is accepted in refresh input.

| Method | Path after /api/v1 | Behavior |
|---|---|---|
| GET | /matches | Own stored recommendations; page/page_size, minimum_score 0Ã¢â‚¬“100, eligibility, required_coverage 0Ã¢â‚¬“1, location, source_id, employment_type, work_arrangement, include_stale |
| POST | /matches/refresh | Synchronous committed batch; limit 1Ã¢â‚¬“200; optional job_ids at most 200 or after_job_id cursor; complete/partial counts, has_more and next_job_id |
| GET | /matches/{job_id} or /jobs/{job_id}/match | Own not_calculated/current/stale pair; no implicit calculation |
| GET | /matching/status | Own current/stale/uncalculated counts, profile completeness, configuration and last refresh |

Unknown scores are null. Not-calculated responses contain no fake match. Normal recommendations exclude unavailable listings and confirmed explicit mismatches; unknown eligibility remains labeled. Previous results require include_stale and remain labeled. Input bounds and UUID validation return 422, unknown requested jobs return 404, an overlapping own refresh returns 409, and database failure returns safe 503 with transaction rollback. Preferences accept optional current_country; it is not inferred from target locations and cannot establish work authorization. See [methodology](matching-methodology.md).


## Phase 4 discovery contract

`GET /jobs` retains items/total/page/page_size and adds a private page-ID-keyed `assessments` sidecar, lexical `text_relevance`, `search_version` and interpretation notices. Single-job public presentation is unchanged. Query schemas now centralize validation in `modules/search/schemas.py`; all filtering/count/order/page operations use `modules/search/query.py` through the existing jobs service. See [search architecture](search-architecture.md) for the complete lexical/filter/missing-data policy.

Added sort values: text_relevance, candidate_match, verified_desc and employer; legacy recent/title/published_desc/salary_desc remain. Added criteria: country, bounded skills/employment_types/work_arrangements lists, availability_scope (available/all/requires_verification), verified_after, experience_min/max, minimum_score, eligibility, required_coverage and match_state (any/current/stale/missing/insufficient). Scalar legacy criteria remain. Salary filtering/sorting requires comparable currency and pay period. Date thresholds require timezone offsets. Expired presentation from an elapsed integrated-source deadline also governs status filters in historical views; source rows are not rewritten.

`GET /jobs/suggestions?q=...&limit=...` returns grounded title/employer/location/structured-skill values (query max 100, limit 1Ã¢â‚¬“12; fewer than two normalized characters returns empty). `POST /jobs/compare` accepts 1Ã¢â‚¬“3 distinct job UUIDs and returns source-presented jobs, extracted requirements when available and only the session candidate's stored pair assessment. No implicit matching calculation occurs.

Saved-search GET/POST/PATCH/DELETE and owned POST /saved-searches/{id}/use are documented in [job-comparison.md](job-comparison.md). Definitions use SearchCriteria, with extra keys forbidden and no page/profile identity/job payload. Max 50 per candidate, case-insensitive unique name, own-only lookup, commit before success. Search/saved-search pages are bounded to 10,000 and page size to 100. Unowned definitions return 404; invalid criteria/bounds 422; duplicate names/quota 409; unauthenticated requests 401. Existing error redaction/origin checks remain.

## Phase 5 resume contract

See the [complete resume endpoint table and request semantics](resume-architecture.md#private-api). Raw PDF/DOCX uploads use Content-Type and URL-encoded X-Resume-Filename headers, authenticated own-profile resolution, backend byte/structure limits and private storage. Evidence, review and confirmation are separate endpoints; accepting alone never writes a profile. Explicit confirmation requires preview revision/profile fingerprint, selected accepted proposal IDs and an idempotency key. Conflict resolution is deliberate. Deletion may return 202 deletion_pending for recoverable cleanup. Internal storage references and paths are never response fields.

## Phase 6 Career Intelligence

`POST /api/v1/career/overview` accepts an optional-filter JSON object and returns a typed shared career dashboard. It requires the existing session and derives only the current candidate. Filters: target_role/origin_role/location (bounded strings), source_id UUID, timezone-aware published_after (inclusive) / published_before (exclusive), and requirement_kind all/required/preferred. No user/profile ID is accepted. Profile/source missing: 404; invalid filters: 422; anonymous: 401; database errors: safe 503. Origin choices must be recorded employment titles or observed scoped listing titles. No profile/matching write or remote resource lookup occurs. See [population/evidence/response semantics](career-intelligence.md).


## Phase 7 authenticated routes

All are under `/api/v1`. No recipient or candidate ID parameter can grant access to another account.

| Routes | Purpose |
|---|---|
| GET/PUT `/notifications/preferences` | Own channel/global preferences, capability status |
| GET `/notifications` | Own paginated delivered records; optional include_history/unread_only |
| GET `/notifications/{id}`, PATCH `/{id}/read`, POST `/notifications/read-batch` | Owned delivery/read state; bounded atomic batch |
| GET/POST `/alerts`, PUT/DELETE `/alerts/{id}`, GET `/{id}/activity` | Owned subscription lifecycle; optimistic revision, frozen criteria |
| GET/POST `/reminders`, PUT `/reminders/{id}`, POST `/{id}/action` | Owned application reminders; explicit wall time/zone/fold and revision |
| GET `/automation/status`, `/automation/tasks`, `/automation/deliveries` | Operator-only actual queue/run/delivery evidence |
| PUT `/automation/sources/{id}/schedule` | Operator-only source schedule interval/cap/pause |
| POST `/automation/tasks/{id}/retry` | Operator-only explicit retry of safe failed DB/interruption tasks |
| POST `/automation/deliveries/{id}/reconcile` | Operator-only recorded uncertain outcome; evidence required, no resend |

Creates return 201. Ownership misses return 404, operator violations 403, invalid criteria/timezones/unconfigured email 422, stale revisions/unsafe retries 409. Unknown fields are rejected. No unauthenticated task-tick endpoint is exposed. Existing sessions, CORS/origin checks and application history remain authoritative.
