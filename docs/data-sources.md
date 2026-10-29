# Job-source assessment and integration

Assessed on 27 October 2026. The implemented source is **Himalayas**. This is a remote-job feed with worldwide and country-restricted roles; it is not a promise of India eligibility or candidate relevance.

## Selection evidence

| Source | Official documentation and access | Decision |
|---|---|---|
| Himalayas | [API reference](https://himalayas.app/docs/remote-jobs-api), [OpenAPI](https://himalayas.app/docs/openapi.json), [API user terms, clause 113](https://himalayas.app/terms). Public browse and single-job requests returned HTTP 200 without credentials. | Selected: explicit permission for this app's display, bounded cursor pages, stable identity, salary periods, country restrictions and a documented availability check. |
| Arbeitnow | [Founder-maintained API announcement](https://www.arbeitnow.com/blog/job-board-api) describes public, keyless European/UK listings and links its API documentation. Access/terms were researched but this task did not execute a live Arbeitnow integration. | Deferred: narrower geographic coverage and no need for a second provider in this phase. Do a separate current terms/rate-limit assessment before enabling. |
| Remotive | [Provider's API repository](https://github.com/remotive-com/remote-jobs-api) and [current terms](https://remotive.com/terms-of-use). Its broader redistribution restrictions require careful reconciliation with the intended use. No live integration was attempted. | Deferred: Himalayas supplied a clearer documented permission path for this product; no permission is inferred from a viewable page. |

## Permission and attribution

Himalayas' API-specific terms permit personal/commercial display on apps the integrator operates. Every original-vacancy/apply action must retain the supplied `applicationLink`; visible source credit links to Himalayas. The UI implements both. Do not export these records onward to other job boards, search engines, aggregators, external feeds or JobPosting structured data. This project provides no syndication feature and makes no external application submission. Keep source access within the documented limits, cache appropriately and remove unavailable listings from candidate discovery. No scraping of protected job pages is used.

This is an implementation assessment of the published permission, not independent legal advice or a guarantee the terms will never change. Recheck the linked official conditions before a public rollout or new data-sharing use.

## Requests and configuration

- Browse: fixed `https://himalayas.app/jobs/api`, `limit=20`; echo an opaque `nextCursor` as `cursor` until absent. The deprecated offset path is not used.
- Availability: fixed `https://himalayas.app/jobs/api/companies/{company}/jobs/{slug}` derived only from a strictly validated source GUID. 200 confirms open, 410 confirms closed, 404 means unknown/not found rather than proof of closure.
- No key is required for public access. Optional `HIMALAYAS_API_KEY` is a server-only environment secret, never a URL, database field, response or frontend variable.
- Official keyed limits at assessment: 60/minute and 10,000/day; public feed access shares an allowance whose numeric ceiling is not documented. Single-job public checks document 60/minute. The transport spaces requests by at least 1.1 seconds and respects rate-limit cooldowns.
- The feed is refreshed/cached on a daily cadence; the single-job check can be cached for up to ten minutes. The optional scheduler therefore has a minimum 24-hour interval. No schedule starts inside the API.
- Each source defaults to **two pages per batch** (up to 40 observed records). A `limited` run means its configured batch ended with a continuation; it does not claim full-feed coverage. `last_full_sync_at` is recorded only for a successful, uninterrupted walk beginning at the first page and ending without continuation.

`python -m app.ingestion.cli configure --page-limit 2` creates/enables the installed source. See [ingestion.md](ingestion.md) for sync, optional scheduling, continuation and recovery commands. No separate third-party credentials were needed for the observed live verification.

## Field interpretation

| Provider fact | Canonical handling |
|---|---|
| guid | Stable external ID, unique together with local source ID; only the documented HTTPS host/path accepted |
| applicationLink | Preserved unchanged in `source_url`; no employer/ATS replacement |
| title, companyName, description | Validated required fields; descriptions become plain text with scripts/styles discarded |
| pubDate | **source_updated_at**. Provider describes modification time; original `published_at` stays NULL |
| expiryDate | Source maximum listing deadline in `source_expires_at`; elapsed deadline is labeled a derived assessment |
| employmentType | Known explicit values map to the existing enum; unfamiliar/unsupported values remain unknown |
| salary values/currency/period | Preserve the disclosed unit and currency; annual/hourly/weekly/fortnightly/monthly map to year/hour/week/fortnight/month; no FX or annualization |
| locationRestrictions | Full country list retained separately; explicit empty array means source-reported worldwide; omission stays unknown |
| timezoneRestrictions | Preserve provider values, including numeric offsets observed live |
| categories | Source taxonomy only; not invented required skills or eligibility evidence |

Live responses differed from portions of the OpenAPI: location arrays contained country strings and timezone arrays contained numbers. The adapter accepts those observed forms as well as documented location objects/string timezones. The source's original publication date, required skills, responsibilities split and experience-year ranges are not guessed from text.

Optional omissions/nulls do not erase previously collected non-null values. Explicit empty restriction arrays are authoritative empty values. Salary amounts travel with their currency/period: changing that pair never relabels an old retained bound. Invalid merged ranges are rejected with a record-level diagnostic, preserving prior data.

## Adding a source

1. Record official endpoints, terms, permitted display/storage, cadence, fields and access evidence.
2. Implement `JobSourceAdapter` in `app/modules/sources/`: page retrieval, identity, normalization and verification. Return `SourcePage`, `NormalizedJob` and `Verification`; raise safe `SourceError` codes.
3. Keep network destinations fixed/allowlisted and credentials server-side. Never fetch a user-configured arbitrary URL.
4. Register the adapter explicitly in the worker/control layer; merely adding a database row does not install executable integration code.
5. Add representative synthetic fixtures, error/partial-update tests and a bounded live verification. Reuse canonical persistence and run accounting; do not introduce provider fields into ingestion orchestration.

Current installed adapter registry contains only Himalayas. Source status and live results are documented in [phase2-validation.md](phase2-validation.md) and the durable database run ledger.
