# Phase 7 completion and verification

Verification date: 29 October 2026, Asia/Kolkata. Final exact test results and source review are recorded in `phase7-verification-evidence.json` and `phase7-file-review.json` beside this report.

## Implemented behavior

Phase 7 extends the existing FastAPI/PostgreSQL/React application. Persistent source job events feed bounded background tasks, explicit owned alert subscriptions, transactional notifications/channel outbox and numbered delivery attempts. The existing CLI worker and source scheduler handle source work and downstream processing. In-app delivery, persisted read/unread state, explicit application reminders, preferences and protected operational controls are implemented. Optional STARTTLS SMTP has conservative outcome handling. No separate matching formula was added.

Source schedules default off and require an operator to configure them. Global job alerts and email default off. Saved searches remain definitions until a separate subscription is created. Edits/resumes start a future-only window. New events and opted-in material updates use current search criteria; score/coverage/eligibility conditions require current assessed matching evidence. Unknown, closed, expired or insufficiently verified jobs cannot generate active-job alerts. Missing/stale scores are skipped without implicit recalculation. Overlapping subscriptions deduplicate to one candidate/event notification.

Reminder creation requires an owned application, explicit wall time and IANA zone. DST gaps are rejected; repeated times require first/second occurrence. Revision checks prevent stale edits, obsolete tasks and pending deliveries. Completion/cancellation/withdrawal suppress pending delivery, application deletion cascades reminders, and existing status history is preserved. A reminder marked notified means a notification was queued; channel state establishes delivery.

## Source verification and genuine records

The authorized live run used the original queue, normalization, verification, transport and persistence pipeline, capped at one page. It fetched and accepted 20 genuine listings, inserted 20, and recorded zero rejects/skips/retries/errors. Status is `limited`, meaning the bounded page succeeded and continuation remains; this was not a full-feed sync. All original 80 job IDs and their original stored values remain intact. The current feed page did not contain those original records, so none of the original 80 was reverified.

The resulting dataset contains 100 genuine jobs, with 20 eligible for active alerts at the dated final check. Twenty persistent new-listing events and tasks were created. The real local worker completed those tasks. There are zero real candidates/subscriptions and zero real notifications: no live personalized alert delivery is claimed. Source details and observation time are in `phase7-live-sync-evidence.json`. No synthetic records were written to the genuine database.

## Reliability and regression evidence

The original 224 backend tests remain part of the final combined suite. Phase 7 tests cover valid verification reuse and re-verification after the ten-minute interval, persisted eligibility, meaningful/unchanged/availability events, concurrent canonical persistence, transaction rollback, current/stale/insufficient scores, subscription ownership/preferences, outbox idempotency, task leases/fencing/recovery, source retry lineage, shared request spacing, reminder ownership/revision/withdrawal/deletion and DST boundaries. SMTP protocol/adapter tests exercise safe temporary/permanent failures and uncertain acceptance without contacting a provider.

The browser suite exercises Phases 1–7 against an isolated `_browser` database and real HTTP/PostgreSQL. The Phase 7 journey creates a subscription, ingests an explicitly synthetic fixture through the real ingestion service, executes the real worker, checks persisted delivery/read state and repeat-ingestion deduplication, manages reminders, tests operator authorization and schedule controls, and checks the mobile layout. Desktop operations and mobile notification screenshots are included. Synthetic tests establish software behavior, not independent real-world matching quality.

Browser testing found and fixed a real reminder-form race: late-loading timezone preferences could remount the form and clear a just-entered date. The form now waits for preferences before accepting input. Existing source-screen mocks gained responses for the newly added operations endpoints; existing regression assertions were retained. The longer Phase 7 browser journey has a 120-second test budget to accommodate its real worker subprocesses and database calls.

`0006_automation` adds nine tables and additive job/run columns plus reminder ownership constraints. Live schema comparison passes. A separate populated `_test` database passed upgrade, downgrade and re-upgrade while preserving every original column/value, including saved jobs/searches, application events, matching results and resume metadata. Production/development data was never downgraded or reset. Before-sync and after-sync hash evidence identifies the authorized source/run/audit additions.

The database process was interrupted during the session. Restarting the existing cluster completed PostgreSQL recovery; a subsequent original-column hash check passed before live synchronization. This is observed local recovery, not a production backup/restore qualification.

## Notifications, security and operational limits

Logical notification/outbox writes are transactional. In-app publication is atomic. Database/interruption retries are bounded; expired sending email becomes uncertain and is not blindly resent. Operators can reconcile uncertain outcomes with evidence, without sending again. Provider pacing persists across worker/run boundaries; source Retry-After and existing cooldowns remain authoritative. A valid verification is reused only within the existing ten-minute cache interval; the 24-hour active-alert freshness gate remains separate.

Authentication, server-side ownership, composite reminder/application ownership, operator checks, fixed provider origin, certificate validation, bounded input/payloads and private error categories are retained. Source text is rendered as text. Email templates contain generic authenticated workspace/preferences links, excluding imported job-feed descriptions, resumes, profile details and private reminder notes. Dependency audit results are in the final evidence file; these checks are not a production security certification.

SMTP credentials and a controlled real test recipient are not configured. Real SMTP acceptance/inbox placement remains unverified. In-app delivery is verified in isolated candidate workflows; genuine eligible listings have not produced a real candidate notification. No employers were contacted and no applications were submitted externally.

Local API/web/worker execution was verified during the session, with schedules disabled. These processes are not supervised and may stop between sessions; start them using the documented commands. Startup/shutdown and recovery commands are in README and `automation-architecture.md`; local process IDs are recorded in the workspace runtime file. API readiness alone does not prove worker supervision. Unattended restart, HTTPS deployment, backup validation, production monitoring/privacy controls and operational readiness remain Phase 8. Digests/quiet hours and a delivery-time guarantee are not implemented. Missing-score events are not replayed later after a matching refresh.

## Acceptance and source review

The Phase 7 local acceptance gate is met only with passing final regression/build/schema/browser evidence. Real email and genuine personalized delivery remain explicitly unverified for the configuration reasons above. The final evidence file records the gate result and exact counts. Source review uses SHA-256 against the preserved Phase 6 baseline because this directory is not a Git checkout. Prior archives/historical screenshots and the complete matching module are preserved. Runtime credentials, databases, private storage, dependencies and logs are excluded from the archive. No Git commit, push, branch publication or remote-CI action was performed. Work stops at Phase 7; Phase 8 was not started.
