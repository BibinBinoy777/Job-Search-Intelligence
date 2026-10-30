# Backup and recovery

Run from apps/backend. Supply PostgreSQL native pg_dump/pg_restore client tools compatible with the server major version. The verified server is 18.4; separately obtained 18.x client tools do not replace or upgrade that server. Official Windows binary distributions are linked from https://www.postgresql.org/download/windows/ and https://www.enterprisedb.com/download-postgresql-binaries .

```powershell
python -m app.operations.cli backup --destination <private-backup-root> --pg-bin <client-bin>
python -m app.operations.cli verify-backup --backup <backup-set>
python -m app.operations.cli restore-test --backup <backup-set> --pg-bin <client-bin>
```

Backups must be outside source/web/document roots. Creation holds SHARE table locks, exports a REPEATABLE READ snapshot, dumps native custom format with that snapshot, and copies referenced resume objects. This briefly blocks writes to obtain a compatible recovery point. Lock acquisition times out after five seconds; native tool runtime is bounded. Missing/unreadable/mismatched references fail the set, with a FAILED marker. Unreferenced files and parser temporary directories are excluded. The manifest records identity/time, server version, revision, all table counts/value hashes, dump hash, and document hashes/sizes. Manifests contain private metadata.

Native archive listing establishes readability, not restoration. Restore-test creates a new uniquely named _restore_test database and new document directory, restores and compares every table hash and document reference/checksum. It never overwrites development/production. Failed restores retain an isolated environment for investigation and never receive a success proof. Disposable restoration environments are retained for inspection; remove only explicitly identified test databases/directories later.

Optional Windows encryption:

```powershell
python -m app.operations.cli encrypt-backup --backup <verified-set> --output <new-envelope.dpapi>
python -m app.operations.cli decrypt-backup --envelope <envelope.dpapi> --destination <new-private-directory>
```

DPAPI keys are managed by the Windows user profile, separately from the envelope/source. Same-account encrypt/decrypt/restore is tested; portable recovery after losing that profile is not qualified. Protect Windows key/profile recovery independently. Envelopes are capped at 256 MiB; overwrites/path traversal are refused. Plaintext originals remain and must have restricted filesystem access. Encrypting a copy does not encrypt existing plaintext sets. Windows chmod is not proof of restrictive ACLs; configure service-account-only storage/backup ACLs before production personal data. Never publish dumps, envelopes, manifests or keys.

Retention defaults: seven recent verified sets, newest from four weeks and twelve months. Preview is default:

```powershell
python -m app.operations.cli retention --directory <backup-root>
python -m app.operations.cli retention --directory <backup-root> --apply
```

Only integrity-valid restore-verified sets are eligible. The newest known-good set is retained; unknown/failed sets require manual review. Deletion targets are resolved beneath the explicit root and symlinks are refused. Resume originals are never backup-retention targets.

Recovery: stop applications; select/validate/decrypt one compatible set; restore into isolation; inspect schema, hashes and document relationships; preserve the old database/storage; explicitly configure a replacement only after operator review; apply reviewed forward migrations when required; restart and check readiness/worker/owned downloads. If validation fails, retain the old instance and investigate the isolated restore. Never downgrade the only working database as a routine test.

Provisional RPO target: 24 hours only if an operator actually takes daily compatible backups. No automatic backup schedule or loss guarantee is claimed. Native restore/validation measurements in phase8a-backup-evidence.json apply to this small local dataset, not production throughput or total disaster RTO. Full cold-start/operator recovery time is unmeasured.
