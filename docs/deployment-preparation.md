# Deployment preparation and migration safety

Phase 8A is local preparation. Phase 8B covers hosting, public HTTPS/DNS, least-privileged services, unattended boot supervision, independent monitoring, off-host backup/key recovery, real email and internet-access/security qualification. A purchased domain is optional.

Settings distinguish development/test/production; .env.example contains placeholders. Production requires configured PostgreSQL credentials, secure cookies, exact HTTPS CORS/app origins, explicit public trusted hosts, debug disabled and storage outside source/web roots. Known weak/default or missing DB credentials are rejected. The portable local bootstrap role is not a production role. Server secrets never belong in frontend variables.

Use locked Python/npm dependencies. Review Alembic history/current and restore-test a compatible DB/document backup before changing a working instance. Upgrade explicitly with `python -m alembic upgrade head`; compare with `python -m alembic check`. Startup never migrates without explicit -Migrate.

0007_local_operations additively introduces recovery-token hashes/expiry and default-false pending-deletion state. It does not replace jobs/profiles/matching/outbox data. Downgrade destroys recovery-token and pending-deletion state; it is not a general recovery procedure. Prefer corrective forward migrations or a compatible verified backup restored into a replacement environment. Never blindly downgrade the only working database. Restore tests compare every table value and document mapping. Rotate credentials in private configuration, restart and verify relevant services, and revoke sessions/recovery credentials when appropriate; no secret rotation is implicit.

The parser boundary reduces credential exposure and contains ordinary malformed/resource-heavy input; public intake still needs a stronger OS/service identity boundary and scanning policy. Real email recovery, distributed throttling, production ACLs, public HTTPS/cookie/proxy behavior and off-host disaster recovery require hosted testing. Local tests and dated dependency audits are not production certification.
