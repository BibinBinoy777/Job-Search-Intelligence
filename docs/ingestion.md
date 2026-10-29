# Phase 2 ingestion operations

The API and frontend work without an ingestion process. Network calls happen in a separate operator/worker process. The existing PostgreSQL job table remains authoritative; no second job system or distributed queue was added.

## Pipeline and transactions

`control.py` validates/enqueues a durable run. `HimalayasAdapter` fetches a bounded page; `JsonTransport` handles HTTPS, timeouts, pacing, byte limits and retries. The normalizer validates identity/links, strips HTML and produces canonical data/provenance. The freshness service evaluates verification evidence. `persistence.py` applies partial updates and conservative duplicate flags. `service.py` coordinates these pieces and records outcomes.

Each source has at most one queued/running run, enforced by a partial unique index. A PostgreSQL session advisory lock coordinates workers and local synchronous CLI runs across page commits. A second worker cannot process a claimed source. Locks are explicitly released and also disappear when the worker's database connection dies.

Network requests run outside database write transactions. A committed page transaction includes all valid job changes, individual record outcomes, counters and the next cursor. Per-record savepoints isolate malformed merged records from other valid records. A crash cannot commit page counters without the corresponding job/record writes. A terminated worker can leave a run marked running; operator recovery first proves the source lock is no longer owned, then marks it interrupted. It never invents completion.

## Local commands

From `apps/backend`, with the virtual environment's `python` and migrated PostgreSQL:

```powershell
python -m alembic upgrade head
python -m app.ingestion.cli configure --page-limit 2
```

The configure command prints the actual source UUID. Use that value below:

```powershell
python -m app.ingestion.cli sync --source-id <source-uuid>
python -m app.ingestion.cli sync --source-id <source-uuid> --queue-only
python -m app.ingestion.cli worker --once
```

Without `--queue-only`, sync runs the bounded batch in the CLI process and prints actual counters. The HTTP trigger only queues work and returns **202 with the run ID**; it never performs network ingestion inside the API request. For queued API/CLI requests, run the worker separately:

```powershell
python -m app.ingestion.cli worker
```

Use Ctrl+C to stop that process. It checks every five seconds; scheduling is not enabled merely by starting it.

### Operator access in the UI

Register a normal local account through the app first. A trusted local operator with database/config access may grant that exact account the role:

```powershell
python -m app.ingestion.cli promote --email <existing-account-email>
python -m app.ingestion.cli promote --email <existing-account-email> --revoke
```

Promotion is explicit, audited and creates no account/password. Existing users migrate with `is_operator=false`. The **Data sources** page is readable by authenticated candidates; queue/resume buttons appear only when the backend grants operator capability. The API checks the role independently. Refresh the page after a role change.

### Optional scheduling

```powershell
python -m app.ingestion.cli configure --page-limit 2 --schedule-hours 24
python -m app.ingestion.cli worker --schedule
```

This stores the next due time; the worker enqueues due sources under row locks, with the active-run unique index as a second guard. Multiple scheduler copies cannot enqueue simultaneous runs for the same source. Sources disabled or in rate-limit cooldown are not scheduled. A schedule does not run unless this explicit process remains alive. Reconfigure without `--schedule-hours` to disable it. Windows Task Scheduler or a process manager may supervise this documented command; none was silently installed during this task.

### Continuation and interruption

```powershell
python -m app.ingestion.cli sync --source-id <source-uuid> --resume-run-id <finished-run-uuid>
python -m app.ingestion.cli recover --run-id <interrupted-run-uuid>
```

A finished limited/partial run with a stored continuation can start a new run from its last checkpoint. Recovery refuses to steal an active worker's lock. If failure occurred before a non-null continuation was available, start a fresh sync; source identity makes restart idempotent. A resumed suffix is not a complete feed walk. Fresh runs intentionally start at the first page to collect recent changes. Permanent malformed records have explicit rejected outcomes; resuming moves past them, while a fresh walk can re-evaluate corrected source data. Verification-budget failure retains the failed page cursor where available so that page can be replayed safely.

## Outcomes and accounting

Run states: queued, running, completed, limited, partial, failed and interrupted. `completed` reached the end of the selected feed walk with no record errors; `limited` reached the configured page budget with more pages available. Neither queued nor running claims completed work. Record failures make the run partial. A page-fetch failure before any committed page is failed; after prior pages it is partial. No failed run advances last-success time.

Counter identities are database constrained:

```text
fetched = accepted + duplicates + rejected + skipped
accepted = inserted + updated + unchanged
```

`fetched` counts records on successfully processed pages. `duplicates` counts repeated source identities delivered again within that run, while a stable record from a prior run is accepted as updated or unchanged. `rejected` means malformed or inconsistent canonical data. `skipped` means valid or unprocessed records whose availability could not be established after an operational failure. `errors` counts rejected/skipped outcomes plus terminal page/run failures; it is not part of the fetched identity. `retried` counts extra HTTP attempts actually made. Failed fetch pages with no records never add fictitious fetched records.

Record diagnostics store page/index, a source-identity hash, optional canonical job ID, outcome and a fixed safe code. They do not store raw provider bodies, descriptions, headers, tokens or credentials. Finished-run API reconciliation groups these records and checks the persisted counters. Reconciliation waits until a queued/running run finishes to avoid reporting a moving checkpoint as an inconsistency.

Retain run/record diagnostics for 30 days by operational policy, with a separately approved database maintenance job if needed; automatic deletion is not enabled. At the hard page cap, one run has at most 500 record diagnostics. This policy does not authorize deletion of candidate saves, applications or canonical jobs.

## Deduplication and partial updates

The existing unique `(source_id, external_id)` constraint and PostgreSQL conflict handling prevent concurrent duplicates. Unchanged observations update last-seen/provenance without advancing material-update time. Source modification time or payload hash alone does not create a material change. No job-version records are manufactured.

Cross-source review requires corroborating normalized description, title, employer and either location or original URL. It writes an independent duplicate-candidate relationship and preserves both records and provenance. Title alone is insufficient; no ambiguous merge or deletion happens automatically.

Optional omissions/nulls preserve earlier known facts; explicit empty restriction arrays may clear restrictions. Salary currency and period must remain consistent with their amounts. Required fields and merged ranges are revalidated before writes.

## Freshness and availability

- First seen: first successful canonical insert; never reset on repeat.
- Last seen: last accepted source observation; a verification-only failure does not overwrite canonical data or pretend acceptance.
- Last verified: actual single-job API check time. Reused verification inside the ten-minute cache window retains the old timestamp; ingestion does not fabricate a new verification.
- Source updated: provider modification timestamp. Publication remains unknown when not separately supplied.
- Material updated: canonical content, requirements/restrictions, deadline or status evidence changed.
- Active: single-job endpoint confirmed open.
- Closed: single-job endpoint explicitly returned 410.
- Unknown: verification returned 404 or reliable status is unavailable; never silently treated as closed.
- Expired: documented source deadline elapsed; labeled `source_deadline_elapsed`, not falsely claimed to be a live closure check.

Missing a listing in a search or bounded page never closes it. Source failure preserves jobs and status. Integrated listings disappear from discovery when their deadline passes, they are closed/unknown, or availability verification is older than 24 hours. That last rule is a **platform freshness assessment**, not a source-confirmed closure. Unavailable/stale details suppress vacancy text, salary/skills and apply links while retaining identity for private save/application history. Legacy/manual Phase 1 records retain their existing unknown-status behavior.

The worker never scrapes job pages. It uses the documented verification endpoint. Previously verified records can remain discoverable during an outage until the explicitly documented 24-hour evidence window elapses.

## Failure and retry policy

Default socket timeout: 10 seconds. Stream deadline: 40 seconds. Decoded JSON byte ceiling: 3 MB. Redirects and arbitrary external destinations are refused. At most three attempts per request, for network failures, 408/429 and selected 5xx responses; permanent authentication/permission/validation errors are not retried. Requests are spaced by at least 1.1 seconds.

Retry-After seconds or HTTP dates are honored. If the required delay exceeds 30 seconds, the worker records the cooldown and stops rather than sleeping indefinitely or retrying too soon. Run creation refuses a source whose persisted cooldown has not elapsed. Exhausted verification failures stop further source requests in the page, record remaining skips and finish visibly partial. There is no simulated successful empty result.

If PostgreSQL itself is unavailable, a worker cannot guarantee writing its failure record until connectivity returns. Use the heartbeat/run state and explicit recovery once the source lock is unowned. No automatic stale-run takeover guesses that a slow active worker is dead.
