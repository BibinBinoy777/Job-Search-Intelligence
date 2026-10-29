# Job comparison and saved searches

## Comparison

Select **Compare** on a job card or detail, then **Compare selected jobs**. At most three distinct jobs can be selected. Selection survives ordinary navigation in memory; the comparison URL contains only public job UUIDs and can restore the view. Removing a column or clearing selection is explicit. Page reload need not restore the in-memory discovery tray, but a valid comparison URL remains usable.

Authenticated `POST /api/v1/jobs/compare` accepts `job_ids` (1–3 distinct UUIDs) and returns typed comparison items in requested order. Missing jobs return 404, duplicate/excess IDs 422 and missing authentication 401. It reuses canonical job presentation, the Phase 3 extractor and the authenticated candidate's pair-assessment service. No candidate/profile ID is accepted, no score is calculated implicitly and another candidate's result can never be selected by passing a job ID.

The table compares title/employer, source/original link, status/availability, actual publication/verification, location/restrictions, work mode/type, salary with currency/period, structured/extracted experience expectations, required/preferred skills, qualifications and responsibilities. Extracted requirements are labeled and can be inspected against the source. Missing values say unknown/not provided/not identified. Those phrases are distinct from a confirmed absence. Unavailable integrated listings retain identity/tracking references while source content/apply links are suppressed. Original links open independently; no external application is submitted.

Candidate rows are explicitly separate: current recorded relevance, recognized eligibility, assessed scoring weight, required skills evidenced/not evidenced, experience/preference components and unresolved conditions. Stale assessments show a refresh instruction and do not contribute a displayed comparison score. Missing profiles/assessments and insufficient evidence remain distinct from zero. "Not evidenced" is not proof that a person lacks a skill. Scores are not employment probabilities, and their real-world quality remains independently unvalidated.

Save/unsave and Track application reuse existing endpoints and server ownership. Success is shown only after confirmed backend writes. An already tracked job can return a visible conflict with a link to the existing tracker. This is a personal record, not an external application. The semantic table has caption, row/column headers, focusable horizontal scrolling on narrow screens, and readable long-field scroll regions. Browser verification covers Chromium desktop/mobile; exhaustive assistive-technology or cross-browser certification is not claimed.

## Saved searches

The existing profile/session architecture supports small owned definitions cleanly. Open **Saved searches** on discovery, name the applied search, and save it. Candidates can list/load, rename, replace criteria with the current applied filters and delete. Loading restores public URL criteria and records `last_used_at`; it does not automatically fetch jobs periodically or send alerts.

`saved_searches` stores profile FK, name/normalized name, validated criteria JSON and created/updated/last-used timestamps. Names and casefolded names fit within 100 characters; names are case-insensitively unique per candidate. A transaction lock and count bound creation to 50 saved searches per candidate. Criteria use the same backend schema as discovery, with unknown fields rejected. Pagination/page size are not saved. No job payload, profile snapshot, credentials, candidate IDs, alerts or schedules are copied into a definition. Loads revalidate persisted criteria to detect schema drift.

All operations resolve the profile from the verified session. List is ownership-scoped; update/use/delete load through the same owned lookup and return 404 for absent/unowned IDs. Mutations share the request's commit-before-success transaction. Backend errors roll back; the UI reports failures without optimistic success. Simultaneous renames/criteria edits currently use last committed write semantics, not an edit-version conflict UI. Saved-search export/import, alerts, history and advanced multi-value editing controls remain future work.

| Method | Path after /api/v1 | Purpose |
|---|---|---|
| GET | /saved-searches | Own paginated definitions |
| POST | /saved-searches | Create validated name/criteria |
| PATCH | /saved-searches/{id} | Rename and/or replace criteria |
| POST | /saved-searches/{id}/use | Revalidate owned criteria and record last use |
| DELETE | /saved-searches/{id} | Delete owned definition |
