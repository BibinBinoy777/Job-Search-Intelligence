# Phase 7 automation architecture

The existing ingestion CLI is the single worker entry point. PostgreSQL stores source runs, page checkpoints, job events, tasks, preferences, notifications, channel outbox rows and delivery attempts. No Redis, Celery, external scheduler or second matching engine is introduced.

From `apps/backend`, after installing the existing requirements and running `python -m alembic upgrade head`:

```powershell
python -m app.ingestion.cli worker --schedule
```

Keep that terminal open. Ctrl+C stops the foreground worker. Stop a hidden local instance by its recorded PID after verifying its command line. Closing the API does not stop a separate worker. The API health endpoint is not a worker health check. The operations page reports the last completed tick and persisted queue states. No worker starts automatically with the API. A supervisor, unattended restart, HTTPS and production alerting remain Phase 8 work.

Each loop coordinates interrupted source runs and retries, processes one existing source run, then at most 10 downstream task chunks and 20 deliveries, and sleeps five seconds. Network synchronization can delay downstream work; these are bounded local workloads, not a delivery-time guarantee. Multiple workers use source/provider advisory locks and SKIP LOCKED row claims. PostgreSQL is the shared coordination boundary; crashed sessions release advisory locks. One provider lock serializes source requests across duplicate configurations.

Source scheduling is off when `schedule_hours` and `next_sync_at` are null. `--schedule` enables checking only configured, enabled schedules. Operators configure a 24–720 hour interval and 1–25 page cap through Data sources. Disabling a schedule leaves manual synchronization available. Manual HTTP synchronization queues the same source run; the CLI `sync --source-id <uuid>` queues and processes it. Existing active-run uniqueness, source locks and cooldown checks apply to every trigger.

The existing provider transport uses fixed allowed origins, certificate validation, no redirects, bounded payloads/timeouts, 1.1 second request spacing and at most three transport attempts. Transient source runs have at most three run attempts; backoff honors a later Retry-After cooldown. Permanent errors stay failed/partial. Committed pages remain usable, failed verification never becomes closure, and a retry replays the last page safely. Running source work with a heartbeat over ten minutes old is marked interrupted only after acquiring its source lock. Review source history before manual recovery with `python -m app.ingestion.cli recover --run-id <uuid>`.

Himalayas feed caching and endpoints were checked against the [official API documentation](https://himalayas.app/docs/remote-jobs-api), [OpenAPI definition](https://himalayas.app/docs/openapi.json) and [API terms](https://himalayas.app/terms). Polling is at most daily through the configured scheduler. API access is public; an optional server-only HIMALAYAS_API_KEY can provide provider-specific quotas. The app retains source credit and original supplied application links; email contains no redistributed job feed.

Automation tasks use queued, running, retry_scheduled, completed, failed and cancelled states, bounded database/interruption retries, a two minute claim lease and fencing by lease timestamp. Fifty subscriptions are evaluated per event chunk. Attempts and safe error categories persist. A processing transaction holds its task lock, so recovery skips genuinely active processing. Exhausted/unsafe failures remain visible and generate in-app operator notices. A restarted worker recovers expired claims. `AUTOMATION_ENABLED=false` pauses downstream processing; it does not disable source synchronization. Source schedules and global candidate preferences have separate controls.

Migration `0006_automation` follows `0005_resumes` additively. It adds nine tables, job event sequence, source-run retry lineage and a composite ownership constraint for reminders. No original record or matching formula is replaced. Downgrading removes Phase 7 data, so use downgrade only in a disposable migration test; preserve production records and backups.
