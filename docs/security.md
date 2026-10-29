# Security boundary and deployment limitations

Phase 2 adds an explicit server-side operator role (false for existing/new accounts), authenticated source/run reads and operator-only queued synchronization. Local promotion/revocation is audited. External requests use fixed HTTPS API endpoints, validated GUID paths, no redirects, bounded timeouts/size/retries and persisted cooldowns. Keys remain server-side and source HTML becomes inert text. Manual imports cannot overwrite integrated records.

Implemented and tested: Argon2 password hashes, high-entropy opaque session tokens, SHA-256 digests at rest, fixed session expiry, server-side sign-out revocation, HttpOnly/SameSite cookies, origin/cross-site write protection, authentication throttling, strict schema validation, SQL parameter binding, and server-side ownership on every candidate record path. Job source links accept only HTTP(S); React treats imported descriptions as text. The frontend does not receive service secrets or database credentials.

Protected endpoints derive candidate identity from the session and the unique user/profile relationship. Changing an application/child ID cannot expose another user's data or history. Saves are scoped to the candidate even when multiple candidates refer to the same global job. User-controlled fields cannot select an owner. No admin user, shared password or bypass is shipped.

Local HTTP uses `COOKIE_SECURE=false`; production configuration must enable Secure cookies and exact HTTPS origins or startup fails. A single-process, five-minute in-memory limiter is implemented for local registration/login. A production gateway/shared limiter must handle multiple workers, trusted proxy address handling and abuse controls. No distributed limiter is claimed.

## Before exposing this to real users

- Deploy behind HTTPS; keep the API and database private as appropriate, configure a production reverse proxy and security headers/CSP, and validate its origin/proxy behavior.
- Use a dedicated least-privilege database role. The generated portable cluster used for this local verification has a local bootstrap owner; it is not a deployment credential.
- Review email verification, password recovery, password change, session/device management, account deletion, data export/retention and registration policy. Those flows are not implemented in Phase 1.
- Add centralized operational monitoring and alerting, dependency updates/scanning, secure backups and a tested restore procedure. No production uptime or disaster recovery claim is made.
- Review the threat model, capacity limits, audit retention, privacy policy and source permissions for the intended deployment.

Authentication works locally without external provider credentials. There is no MFA or identity-provider integration. The Himalayas API adapter is operational and live-verified; no scraper is installed. No notification, AI, object-storage or resume-provider credential is needed for Phase 1; those integrations remain unimplemented.

The optional application `resume_version_ref` is an opaque user-entered reference with no file access or metadata lookup. Attaching an application to an uploaded version is outside Phase 5; a future attachment workflow must enforce a genuine owned foreign key before granting access. Phase 5 exposes separate authenticated private upload/extraction/download routes; it never interprets this opaque application reference as a filesystem path or an access grant. See [resume security](resume-security.md).

Audit records hold only action names, resource IDs, user IDs and timestamps. They do not store passwords, cookies, job descriptions, profile summaries or resume text. Application notes and correction reasons remain private candidate-owned application data and should be covered by future retention/export/deletion policies.

Tests verify authorization with real registered accounts. Simulated database failures are used solely to verify safe errors and transactional rollback; they are explicitly identified in the validation report.


## Phase 3 matching privacy

Matching uses verified session ownership for every private result, refresh and candidate snapshot. Public job endpoints do not contain candidate assessments. Refresh forbids client candidate IDs and bounds processing to 200 jobs per request. CSRF/origin rules and database error suppression remain active. Concurrent own refreshes serialize via transaction advisory lock; known per-job errors and unexpected database failures have different rollback behavior. Tests cover cross-account isolation, missing authentication, invalid bounds, SQL-error redaction and rollback. Snapshot storage excludes direct identity and employer/school names but remains private professional data; private child IDs and free text must receive ordinary account-level protection. Automated snapshot retention/deletion UI and distributed quotas remain future production work. Dependency audit results are observations for the execution date, not a security certification. See phase3-security-evidence.json.


## Phase 4 discovery privacy

Search parameters are bounded and composed through ORM expressions, not raw input interpolation. Suggestions read public canonical fields only. Matching search joins are scoped to the verified session's profile, with current-input checks before exposing a score; comparison calls the same private pair service. Saved definitions use one owned lookup for update/use/delete and an ownership-scoped list. Creation serializes per candidate and caps definitions at 50; database uniqueness backs normalized names. No candidate ID can be supplied in comparison, saved criteria or search queries to select another account's results. Login clears candidate query caches without replacing the active authentication observer. Default origin/session/no-store/error-suppression controls remain.

The regression suite covers cross-account comparison/saved-search rejection, client-identity rejection, query/range/size limits, invalid criteria, safe database errors, quota and previous phase boundaries. Production load limits/distributed throttling, access-log query redaction policy and broader security testing remain operations work. No alerts, automated external applications or private resume upload are enabled by Phase 4. Dependency audit observations are recorded in phase4-security-evidence.json, not a security certification.

## Phase 5 resume boundary

See [private storage, parser limits, scanning limitations and retention/recovery](resume-security.md). All resume/evidence/review/confirmation/deletion routes resolve the session candidate. No OCR, external AI or actual malware scanner is configured. Synthetic document QA uses only isolated databases/private storage. Phase 5 local verification and advisory results are in [the completion report](phase5-validation.md).

## Phase 6 career privacy

Career analysis resolves the authenticated user's existing profile. Owned resume joins supply skill/provenance references; no raw private resume text, contact/identity fields or employer names are returned in career responses. Public job requirement spans remain traceable to listing IDs. Unconfirmed suggestions do not become profile facts or establish role overlap. Filters cannot supply candidate identity. Existing origin/session/error redaction policies apply. Results are request-local, with no shared personalized cache, runtime resource fetch or extra external service. See [career methodology and privacy](career-intelligence.md) and [verification](phase6-validation.md).
