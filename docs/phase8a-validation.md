# Phase 8A final operational verification

Verification date: 30 October 2026 (Asia/Kolkata). Phase 8A meets its local acceptance gate with the limitations below. This is not production deployment, production encryption qualification, portable key recovery or an OS-enforced document sandbox.

## Exact test results

The combined Phases 1-8A backend suite passed **301 tests, 0 failed, 0 skipped**, including all 280 previous tests and 21 operational/account/crash cases. After two small final changes, four overlapping focused cases passed again: valid-PDF backup/restoration, suppressed configuration-error inputs, pending deletion cleanup, and unauthorized export access. These are not 305 unique tests. Earlier 48/19 targeted runs overlap and are not added to the unique total.

Frontend: **56 passed, 0 failed, 0 skipped**, using one worker to avoid local jsdom resource contention. Browser: **9 passed, 0 failed, 0 skipped**, real Chromium/HTTP/PostgreSQL, preserving the eight previous workflows and adding account export, password/session revocation, explicit deletion with a real synthetic resume and recovery availability. Types/production build, Ruff lint/format, Prettier and schema comparison passed. Final evidence is in phase8a-verification-evidence.json.

## Startup, supervision and failure recovery

PowerShell startup validates an existing cluster, configuration, DB/schema, service ports, API readiness, frontend HTTP and worker state. Only explicit -Migrate changes schema; startup never resets or seeds data. Actual startup, duplicate-start refusal, graceful stop and restart were exercised. PostgreSQL intentionally remains running after application shutdown. The supervisor wraps the existing worker, uses an OS singleton lock and persisted restart/backoff state, and supports cooperative stop markers.

Actual isolated child processes were killed during idle supervision, source ingestion, after an event commit, during reminder processing, and during in-app/outbox or simulated email sending. Tests verify rollback/recovery, lease boundaries, checkpoint replay, duplicate prevention, and holding uncertain email rather than resending. Database-unavailable child startup and supervisor backoff were tested. Earlier durable retry-limit and source cooldown cases remain in regression coverage. Filesystem worker records distinguish a process from a recent heartbeat and current work; a stale observation is not declared healthy. This is session-local supervision, without an installed reboot/logoff production service.

## Database and document recovery

Native custom-format PostgreSQL backups use an exported snapshot while table write locks preserve compatibility with referenced document copies. Manifests contain table counts/value hashes, schema revision, dump checksums and document sizes/checksums. Missing/corrupt objects fail; incomplete backups are never accepted. Native tools were obtained separately because the portable server package lacked pg_dump/pg_restore; the existing server/cluster was preserved.

The genuine 100-job database was actually restored into isolated databases with every table value/hash preserved. It has no candidate resume files; its empty document inventory is not counted as a populated document restore. A separate isolated fixture restored a valid PDF with the exact fixture checksum and correct resume metadata, plus candidate, application/history, saves/searches, two match results, subscription, reminder, notification/outbox and delivery history. The populated restore measured **2.282 seconds** locally. Genuine-data restore measurements were **2.469 seconds** (plaintext set) and **2.360 seconds** (decrypted copy); these include native restore and validation, not total operator disaster recovery. See phase8a-populated-restore-evidence.json and phase8a-backup-evidence.json.

Retention is explicit/previewed and configurable for recent/weekly/monthly verified sets; at least the newest known-good set remains. Unknown/failed sets are retained for manual review. It never prunes live originals. RPO is only a provisional 24-hour target contingent on actual daily backups; no automatic backup schedule, guaranteed RPO or total cold-recovery RTO is claimed.

## Encryption and private storage

Windows DPAPI same-account encryption/decryption and full restored-database verification passed. Tampered envelopes fail safely. Windows user-profile key management is separate from source/envelopes; no key material is committed or logged. Original plaintext backup sets remain present and need restrictive ACLs. Encrypting a copy is not equivalent to protecting all backup files. Off-host recovery after losing the Windows profile/key is unqualified. Production requires an independently recoverable encrypted-copy/key strategy and verified service-account storage/backup ACLs. No original known-good backup was removed.

## Account security and privacy

Recovery tokens are unpredictable, hashed, expire after 20 minutes, single-use and replaced by new issuance. Password recovery/change revokes all sessions and outstanding tokens. Recovery responses avoid account enumeration and are throttled. Ordinary APIs/logs never return credentials; trusted local issuance writes a private file outside source and is disabled in production. Real recovery email is not configured.

Owned export includes versioned JSON/relationships and original private documents, with SQL row/byte and archive limits. Unauthorized access and cross-candidate exclusion are tested. Explicit password plus DELETE MY ACCOUNT confirmation is required for deletion. Durable pending state blocks access before filesystem removal; an injected cleanup failure returned pending and a real retry removed remaining files/metadata. Other candidate and genuine shared job records remain intact. Generic pseudonymous audit metadata and backup copies have separately documented retention. Session listing/revoke-all is available. Automatic legal/audit/log retention and public abuse protection remain operator/Phase 8B concerns, not invented guarantees.

## Parser boundary and monitoring

Existing malformed-file, PDF/DOCX expansion/page/text, quota, timeout, memory/process and ownership protections remain. Parser subprocesses use isolated Python mode, sanitized environment and disposable working directories. Tests verify backend credentials are absent and normal processing cleans its temporary directory. Existing timeout/error/resource tests remain passing. Python socket APIs are denied, but this is not an OS firewall, restricted filesystem identity or protection against arbitrary native exploits. A host crash can leave a temporary orphan requiring verified inactive-object cleanup. Malware scanning is explicitly not configured. Public uploads need stronger OS/service isolation and a real scanning policy in Phase 8B.

Operator-only monitoring reports actual DB/storage state, queue counts and local worker/supervisor/backup observations. Missing/stale/not-initialized/not-configured states are preserved; no uptime values are fabricated. Structured logs emit safe metadata instead of arbitrary payloads, exceptions or credentials. Raw child stderr is suppressed. Real external alerts/SMTP and independently verified production supervision remain unavailable. Runbooks cover startup, backups, account controls, files, monitoring and deployment preparation.

## Migration, preservation, source review and acceptance

Additive 0007_local_operations adds recovery-token storage and a default-false deletion flag. An isolated populated 0006 -> 0007 -> 0006 -> 0007 roundtrip and schema checks preserved original columns/values, including resume, application/history, matching and notification state. Downgrade is documented as destructive for new recovery/deletion state; production recovery should use reviewed forward correction or a verified compatible backup.

Final original-column checks preserve all **100 genuine jobs and all original 80 identifiers**, 80 requirement analyses, five ingestion runs and 180 ingestion records. All candidate/private/history values retain their baseline state. Only the expected running-worker heartbeat timestamp advances. The genuine database still has zero candidates/resumes and no synthetic candidate was created there. Final eligible jobs are **0** because verification aged out naturally; no source synchronization or freshness-rule change was performed in Phase 8A.

Dependency checks reported **0 npm vulnerabilities** and **0 Python vulnerabilities across 45 packages, none skipped**. Gitleaks source review found one reviewed pre-existing role/date false positive in a synthetic career test and no actual secrets; the known local database credential is absent from selected source. Matching-module bytes are unchanged. Final file review/manifests and a portable source archive exclude runtime databases, environment secrets, private storage, backups/envelopes, logs, dependencies and test traces. No Git commit/push/publication or Phase 8B work was performed.

There are no remaining blockers to the scoped local acceptance gate. Public HTTPS/deployment, real email delivery, shared production throttling, unattended reboot supervision, strong OS upload isolation/scanning, restrictive production ACL validation, portable/off-host key recovery and production monitoring remain explicit Phase 8B requirements. Plaintext backup exposure and same-profile DPAPI dependence must be addressed before production personal data. The local process registry is historical evidence, not a claim that services survive session termination.
