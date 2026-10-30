# Local operations

Windows PowerShell, Python with locked requirements, Node with npm dependencies, and the existing PostgreSQL cluster are required. Docker is optional. Build the frontend in apps/frontend with `npm run build` before startup.

From the project root:

```powershell
./scripts/start-local.ps1 -Python <python.exe> -PostgresBin <existing-server-bin> -DataDirectory <existing-pgdata>
./scripts/stop-local.ps1
```

Use full paths, quoting spaces. Defaults: database port 55432, API 8000, frontend 5173. DATABASE_URL and exact allowed origins must match. Startup validates configuration, the existing PG_VERSION directory, database/schema, service ports, backend readiness, frontend HTTP and worker state. It never initializes, resets or seeds a database. Only explicit `-Migrate` applies reviewed migrations. Take and restore-test a compatible backup first. An existing registry/startup mutex refuses duplicate startup; partial startup remains recorded for safe shutdown.

The hidden local supervisor runs the existing worker/scheduler CLI. PostgreSQL source/provider locks and durable task/outbox leases remain authoritative. Source schedules stay opt-in. Unexpected worker exit causes persisted restart/backoff of 2–30 seconds; an OS lock rejects duplicate supervisors. Worker identity, PID, startup/observation times, current phase/task and last completed task are recorded under ignored .local/operations. Process existence alone is not health. Observations older than 45 seconds are stale; long source requests can also cause staleness and need investigation.

Shutdown writes cooperative stop markers, drains the worker's current pass and asks Uvicorn to stop/drain requests. A 60-second process drain timeout reports failure instead of blindly killing work. Frontend preview stops only if its recorded PID still identifies Vite preview. PostgreSQL remains running for other clients. Killed database transactions roll back; committed claims retain recovery leases and interrupted email stays uncertain. Inspect PID command lines before removing an obsolete registry. Never remove a registry merely to bypass live processes.

This is session-local supervision, not an installed Windows service or a reboot/logout availability guarantee. Logs remain private runtime files. No source schedule is enabled by startup. Public deployment and unattended boot supervision are Phase 8B.
