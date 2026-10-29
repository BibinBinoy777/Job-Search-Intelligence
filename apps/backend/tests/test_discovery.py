import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from email.message import Message
from urllib.error import HTTPError, URLError

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.security import utcnow
from app.db.models import DuplicateCandidate, IngestionRun, Job, JobSource, User
from app.db.session import SessionLocal
from app.ingestion.cli import recover
from app.ingestion.control import queue_run
from app.ingestion.persistence import persist_observation
from app.ingestion.service import process_run
from app.modules.sources.contracts import SourceError, SourcePage, Verification
from app.modules.sources.himalayas import HimalayasAdapter
from app.modules.sources.normalization import normalize_himalayas
from app.modules.sources.transport import JsonTransport

P = "/api/v1"


def raw_job(slug="test-engineer", **patch):
    """Synthetic fixtures follow the official API shape, never genuine vacancies."""
    return {
        "title": "TEST ONLY Engineer",
        "companyName": "TEST ONLY Company",
        "description": "<h2>TEST ONLY</h2><p>Build safe software.</p>",
        "employmentType": "Full Time",
        "salaryPeriod": "annual",
        "minSalary": 60000,
        "maxSalary": 90000,
        "currency": "USD",
        "locationRestrictions": ["India"],
        "timezoneRestrictions": [5.5],
        "categories": ["Software-Engineer"],
        "pubDate": 1793000000,
        "expiryDate": 1893000000,
        "guid": f"https://himalayas.app/companies/test-only/jobs/{slug}",
        "applicationLink": f"https://himalayas.app/companies/test-only/jobs/{slug}?utm_source=api",
        **patch,
    }


@pytest.fixture
def source():
    with SessionLocal.begin() as db:
        item = JobSource(
            name="TEST ONLY Himalayas adapter",
            source_type="api",
            adapter_key="himalayas",
            enabled=True,
            page_limit=2,
        )
        db.add(item)
        db.flush()
        return item.id


class AdapterFixture(HimalayasAdapter):
    def __init__(self, pages=None, error_at=None, verification=None):
        self.pages = pages or [SourcePage([raw_job()], None)]
        self.calls = []
        self.verifications = []
        self.error_at = error_at
        self.verification = verification

    def fetch_jobs(self, criteria, cursor=None):
        self.calls.append(cursor)
        if len(self.calls) == self.error_at:
            raise SourceError("provider_unavailable")
        return self.pages[len(self.calls) - 1]

    def verify_job(self, identity):
        self.verifications.append(identity)
        if isinstance(self.verification, Exception):
            raise self.verification
        return Verification(
            self.verification or "active",
            "single_job_api_open"
            if not self.verification
            else "single_job_api_" + self.verification,
            utcnow(),
        )


def execute(source, adapter, resume=None):
    with SessionLocal.begin() as db:
        item = queue_run(db, source, resume_run_id=resume)
        run_id = item.id
    assert process_run(run_id, adapter)
    with SessionLocal() as db:
        return db.get(IngestionRun, run_id)


class Response(io.BytesIO):
    def __init__(self, value, content_type="application/json"):
        super().__init__(value if isinstance(value, bytes) else json.dumps(value).encode())
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.status = 200


def transport_sequence(*items):
    pending = iter(items)
    requests = []

    def opener(req, timeout):
        requests.append(req)
        item = next(pending)
        if isinstance(item, Exception):
            raise item
        return item

    sleeps = []
    retries = []
    return (
        JsonTransport(opener=opener, sleep=sleeps.append, on_retry=lambda: retries.append(1)),
        requests,
        sleeps,
        retries,
    )


def http_error(status, retry_after=None):
    headers = Message()
    if retry_after:
        headers["Retry-After"] = str(retry_after)
    return HTTPError(
        "https://himalayas.app/jobs/api",
        status,
        "untrusted response ignored",
        headers,
        io.BytesIO(b"PRIVATE_PROVIDER_BODY"),
    )


def test_adapter_pagination_and_live_schema_variations():
    transport, requests, _, _ = transport_sequence(
        Response({"jobs": [raw_job()], "nextCursor": "opaque-1"}), Response({"jobs": []})
    )
    adapter = HimalayasAdapter(transport)
    page = adapter.fetch_jobs({"limit": 20})
    assert page.next_cursor == "opaque-1"
    assert adapter.fetch_jobs({"limit": 20}, page.next_cursor).next_cursor is None
    assert "cursor=opaque-1" in requests[1].full_url
    for locations in [["India"], [{"name": "India", "alpha2": "IN"}]]:
        norm = adapter.normalize_job(raw_job(locationRestrictions=locations), "source")
        assert norm.data.location == "India"
        assert norm.metadata["location_restrictions"] == ["India"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"jobs": "invalid"},
        {"jobs": [], "nextCursor": "repeat"},
        {"jobs": [], "nextCursor": 45},
    ],
)
def test_adapter_rejects_changed_page_shapes(payload):
    transport, *_ = transport_sequence(Response(payload))
    with pytest.raises(SourceError):
        HimalayasAdapter(transport).fetch_jobs({})


@pytest.mark.parametrize(
    "change",
    [
        {"guid": "http://127.0.0.1/private"},
        {"guid": "https://himalayas.app.evil.test/companies/x/jobs/y"},
        {"applicationLink": "https://employer.example/apply"},
        {"description": ""},
        {"companyName": None},
        {"title": ""},
        {"pubDate": "yesterday"},
        {"salaryPeriod": "made-up"},
        {"locationRestrictions": [42]},
        {"guid": "http://["},
    ],
)
def test_normalization_rejects_bad_records(change):
    with pytest.raises(SourceError):
        normalize_himalayas(raw_job(**change), "source")


def test_normalization_missing_null_empty_and_untrusted_html():
    raw = raw_job(
        description="<p>Safe <b>text</b></p><script>steal()</script><style>bad</style><p>More</p>",
        locationRestrictions=[],
        minSalary=None,
        maxSalary=None,
    )
    norm = normalize_himalayas(raw, "source")
    assert norm.data.location == "Worldwide"
    assert norm.metadata["location_restrictions"] == []
    assert norm.data.salary_min is None
    assert norm.data.published_at is None
    assert norm.metadata["source_updated_at"].tzinfo is not None
    assert "steal" not in norm.data.description and "bad" not in norm.data.description
    assert norm.data.skills == []  # Taxonomy categories are not invented required skills.
    del raw["locationRestrictions"]
    assert "location_restrictions" not in normalize_himalayas(raw, "source").metadata


@pytest.mark.parametrize(
    ("code", "retry"),
    [(500, True), (503, True), (429, True), (401, False), (403, False), (400, False), (302, False)],
)
def test_transport_retry_and_permanent_statuses(code, retry):
    transport, requests, sleeps, retries = transport_sequence(
        http_error(code, 1), Response({"jobs": []})
    )
    if retry:
        assert transport.get("/jobs/api")[1] == {"jobs": []}
        assert len(requests) == 2 and len(retries) == 1 and max(sleeps) >= 1
    else:
        with pytest.raises(SourceError) as error:
            transport.get("/jobs/api")
        assert len(requests) == 1 and not retries and "PRIVATE" not in str(error.value)


def test_timeout_retry_budget_and_long_rate_cooldown():
    transport, requests, _, retries = transport_sequence(
        URLError("PRIVATE"), TimeoutError(), TimeoutError()
    )
    with pytest.raises(SourceError, match="network_timeout_or_failure"):
        transport.get("/jobs/api")
    assert len(requests) == 3 and len(retries) == 2
    transport, requests, _, retries = transport_sequence(http_error(429, 120))
    with pytest.raises(SourceError) as error:
        transport.get("/jobs/api")
    assert error.value.retry_at > utcnow() + timedelta(seconds=100)
    assert len(requests) == 1 and not retries


def test_response_size_type_json_and_destination(monkeypatch):
    monkeypatch.setattr(settings, "ingestion_max_bytes", 10)
    for response in [Response(b"x" * 11), Response(b"bad"), Response({}, "text/html")]:
        transport, *_ = transport_sequence(response)
        with pytest.raises(SourceError):
            transport.get("/jobs/api")
    transport, *_ = transport_sequence()
    with pytest.raises(SourceError, match="destination_rejected"):
        transport.get("https://127.0.0.1/")


def test_auth_header_stays_server_side(monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "himalayas_api_key", SecretStr("SYNTHETIC_TEST_KEY"))
    transport, requests, _, _ = transport_sequence(Response({}))
    transport.get("/jobs/api")
    assert requests[0].get_header("Authorization") == "Bearer SYNTHETIC_TEST_KEY"
    assert "SYNTHETIC_TEST_KEY" not in requests[0].full_url


@pytest.mark.parametrize(
    ("status", "expected"), [(200, "active"), (404, "unknown"), (410, "closed")]
)
def test_single_listing_verification(status, expected):
    raw = raw_job()
    transport, *_ = transport_sequence(
        Response({"job": raw}) if status == 200 else http_error(status)
    )
    result = HimalayasAdapter(transport).verify_job(raw["guid"])
    assert result.status == expected and result.checked_at.tzinfo is not None


def test_ingestion_insert_repeat_update_and_accounting(source, candidate):
    first = execute(source, AdapterFixture())
    assert (first.fetched, first.accepted, first.inserted, first.errors) == (1, 1, 1, 0)
    assert first.status == "completed"
    with SessionLocal() as db:
        job = db.scalar(select(Job))
        identity, seen, material, verified = (
            job.id,
            job.first_seen_at,
            job.material_updated_at,
            job.last_verified_at,
        )
    second = execute(source, AdapterFixture())
    assert (second.inserted, second.updated, second.unchanged) == (0, 0, 1)
    with SessionLocal() as db:
        job = db.get(Job, identity)
        assert job.first_seen_at == seen and job.last_seen_at >= seen
        assert job.material_updated_at == material and job.last_verified_at == verified
    changed = execute(
        source, AdapterFixture([SourcePage([raw_job(title="TEST ONLY Updated")], None)])
    )
    assert changed.updated == 1
    result = candidate.get(P + "/ingestion/runs/" + changed.id)
    assert result.status_code == 200 and result.json()["reconciled"]
    assert candidate.get(P + "/jobs?q=Updated").json()["total"] == 1


def test_safe_partial_updates_do_not_erase_known_fields(source):
    execute(source, AdapterFixture())
    raw = raw_job()
    for key in [
        "minSalary",
        "maxSalary",
        "currency",
        "locationRestrictions",
        "timezoneRestrictions",
        "employmentType",
    ]:
        raw.pop(key)
    execute(source, AdapterFixture([SourcePage([raw], None)]))
    with SessionLocal() as db:
        job = db.scalar(select(Job))
        assert (
            job.salary_min == 60000
            and job.location == "India"
            and job.employment_type == "full_time"
        )
    execute(source, AdapterFixture([SourcePage([raw_job(locationRestrictions=[])], None)]))
    with SessionLocal() as db:
        assert db.scalar(select(Job.location)) == "Worldwide"


def test_partial_salary_never_relabels_retained_amounts(source):
    execute(source, AdapterFixture())
    execute(
        source,
        AdapterFixture(
            [
                SourcePage(
                    [
                        raw_job(
                            minSalary=None, maxSalary=None, currency="INR", salaryPeriod="monthly"
                        )
                    ],
                    None,
                )
            ]
        ),
    )
    with SessionLocal() as db:
        job = db.scalar(select(Job))
        assert (job.salary_currency, job.salary_period, job.salary_min) == ("USD", "year", 60000)
    execute(
        source,
        AdapterFixture(
            [
                SourcePage(
                    [
                        raw_job(
                            minSalary=2000, maxSalary=None, currency="INR", salaryPeriod="monthly"
                        )
                    ],
                    None,
                )
            ]
        ),
    )
    with SessionLocal() as db:
        job = db.scalar(select(Job))
        assert (job.salary_currency, job.salary_period, job.salary_min, job.salary_max) == (
            "INR",
            "month",
            2000,
            None,
        )


def test_page_repeats_invalid_records_and_partial_accounting(source, candidate):
    r = execute(
        source,
        AdapterFixture([SourcePage([raw_job(), raw_job(), {"bad": True}, raw_job("other")], None)]),
    )
    assert (r.fetched, r.accepted, r.inserted, r.duplicates, r.rejected) == (4, 2, 2, 1, 1)
    assert r.status == "partial"
    result = candidate.get(P + "/ingestion/runs/" + r.id).json()
    assert result["reconciled"] and result["errors"] == 1
    assert candidate.get(P + "/ingestion/runs/" + r.id + "/records").json()["total"] == 4


def test_failed_second_page_keeps_checkpoint_and_resume(source):
    first = execute(source, AdapterFixture([SourcePage([raw_job()], "page-2")], error_at=2))
    assert (
        first.status == "partial"
        and first.pages == 1
        and first.inserted == 1
        and first.next_cursor == "page-2"
    )
    adapter = AdapterFixture([SourcePage([raw_job("second")], None)])
    resumed = execute(source, adapter, resume=first.id)
    assert adapter.calls == ["page-2"] and resumed.inserted == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 2
        assert (
            db.get(JobSource, source).last_full_sync_at is None
        )  # A resumed suffix is not a complete walk.


def test_page_bound_is_visible_and_not_full_source_success(source):
    with SessionLocal.begin() as db:
        db.get(JobSource, source).page_limit = 1
    run = execute(source, AdapterFixture([SourcePage([raw_job()], "more")]))
    assert run.status == "limited" and run.next_cursor == "more"
    with SessionLocal() as db:
        item = db.get(JobSource, source)
        assert item.last_success_at is not None and item.last_full_sync_at is None


def test_outage_and_missing_records_do_not_close_jobs(source):
    execute(source, AdapterFixture())
    failed = execute(source, AdapterFixture(error_at=1))
    assert failed.status == "failed" and failed.fetched == 0 and failed.errors == 1
    execute(source, AdapterFixture([SourcePage([], None)]))
    with SessionLocal() as db:
        assert db.scalar(select(Job.status)) == "active"


def test_closed_unknown_expiry_and_staleness(source, candidate):
    execute(source, AdapterFixture())
    with SessionLocal.begin() as db:
        db.scalar(select(Job)).last_verified_at = utcnow() - timedelta(minutes=11)
    execute(source, AdapterFixture(verification="closed"))
    assert candidate.get(P + "/jobs").json()["total"] == 0
    with SessionLocal() as db:
        job = db.scalar(select(Job))
        assert job.status == "closed"
        result = candidate.get(P + "/jobs/" + job.id).json()
        assert result["is_available"] is False and result["source_url"] is None
    with SessionLocal.begin() as db:
        db.scalar(select(Job)).last_verified_at = utcnow() - timedelta(minutes=11)
    execute(source, AdapterFixture(verification="unknown"))
    with SessionLocal() as db:
        assert db.scalar(select(Job.status)) == "unknown"
    expired = raw_job("expired", expiryDate=1700000000)
    execute(source, AdapterFixture([SourcePage([expired], None)]))
    with SessionLocal() as db:
        item = db.scalar(select(Job).where(Job.external_id == expired["guid"]))
        assert item.status == "expired" and item.status_basis == "source_deadline_elapsed"


def test_verification_failure_keeps_old_data_and_records_skips(source):
    run = execute(
        source,
        AdapterFixture(verification=SourceError("rate_limited", utcnow() + timedelta(minutes=2))),
    )
    assert run.status == "partial" and run.skipped == 1 and run.inserted == 0
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 0
        assert db.get(JobSource, source).not_before_at > utcnow()


def test_duplicate_candidate_requires_corroboration_and_does_not_merge(source):
    execute(source, AdapterFixture())
    with SessionLocal.begin() as db:
        other = JobSource(name="TEST ONLY Second Source", source_type="manual")
        db.add(other)
        db.flush()
        persist_observation(
            db, normalize_himalayas(raw_job(), other.id), Verification("active", "test", utcnow())
        )
        assert db.scalar(select(func.count()).select_from(DuplicateCandidate)) == 1
        assert db.scalar(select(func.count()).select_from(Job)) == 2
        persist_observation(
            db,
            normalize_himalayas(
                raw_job("different", description="Different actual responsibilities"), other.id
            ),
            Verification("active", "test", utcnow()),
        )
        assert db.scalar(select(func.count()).select_from(DuplicateCandidate)) == 1


def test_concurrent_run_lock_and_recovery(source):
    with SessionLocal.begin() as db:
        run_id = queue_run(db, source).id
    entered, release = threading.Event(), threading.Event()

    class Blocking(AdapterFixture):
        def fetch_jobs(self, criteria, cursor=None):
            entered.set()
            assert release.wait(10)
            return super().fetch_jobs(criteria, cursor)

    with ThreadPoolExecutor(max_workers=2) as pool:
        active = pool.submit(process_run, run_id, Blocking())
        assert entered.wait(10)
        assert process_run(run_id, AdapterFixture()) is False
        with pytest.raises(ValueError, match="still owns"):
            recover(run_id)
        release.set()
        assert active.result()
    with SessionLocal.begin() as db:
        interrupted = queue_run(db, source)
        interrupted.status = "running"
        next_id = interrupted.id
    recover(next_id)
    with SessionLocal() as db:
        assert db.get(IngestionRun, next_id).status == "interrupted"


def test_sync_authorization_history_and_filters(candidate, client, source):
    assert candidate.post(P + "/ingestion/sync", json={"source_id": source}).status_code == 403
    with SessionLocal.begin() as db:
        db.scalar(select(User)).is_operator = True
    assert candidate.post(P + "/ingestion/sync", json={"source_id": "bad"}).status_code == 422
    r = candidate.post(P + "/ingestion/sync", json={"source_id": source})
    assert r.status_code == 202 and r.json()["status"] == "queued" and r.json()["fetched"] == 0
    assert candidate.post(P + "/ingestion/sync", json={"source_id": source}).status_code == 409
    assert candidate.get(P + "/ingestion/runs?page_size=1").json()["total"] == 1
    assert candidate.get(P + "/sources/status").json()["can_sync"] is True
    candidate.cookies.clear()
    assert candidate.post(P + "/ingestion/sync", json={"source_id": source}).status_code == 401


def test_new_search_and_currency_period_validation(source, candidate):
    execute(source, AdapterFixture())
    assert (
        candidate.get(P + "/jobs?employer=TEST&title=Engineer&status=active&location=India").json()[
            "total"
        ]
        == 1
    )
    assert candidate.get(P + "/jobs?salary_min=50000").status_code == 422
    assert (
        candidate.get(P + "/jobs?salary_min=50000&salary_currency=USD&salary_period=year").json()[
            "total"
        ]
        == 1
    )
    assert (
        candidate.get(P + "/jobs?salary_min=50000&salary_currency=INR&salary_period=year").json()[
            "total"
        ]
        == 0
    )
    assert (
        candidate.get(P + "/jobs?salary_min=50000&salary_currency=USD&salary_period=month").json()[
            "total"
        ]
        == 0
    )
    assert candidate.get(P + "/jobs?published_after=2020-01-01T00:00:00Z").json()["total"] == 0
    assert candidate.get(P + "/jobs?updated_after=2020-01-01T00:00:00Z").json()["total"] == 1
    assert candidate.get(P + "/jobs?updated_after=2020-01-01").status_code == 422
    with SessionLocal.begin() as db:
        db.scalar(select(Job)).last_verified_at = utcnow() - timedelta(hours=25)
    assert candidate.get(P + "/jobs").json()["total"] == 0


def test_schedule_only_enqueues_once_and_never_bypasses_disabled_sources(source, monkeypatch):
    import app.ingestion.cli as cli

    monkeypatch.setattr(cli, "process_run", lambda *args: False)
    with SessionLocal.begin() as db:
        s = db.get(JobSource, source)
        s.schedule_hours = 24
        s.next_sync_at = utcnow() - timedelta(seconds=1)
    cli.work_once(schedule=True)
    cli.work_once(schedule=True)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(IngestionRun)) == 1
        assert db.get(JobSource, source).next_sync_at > utcnow()
    with SessionLocal.begin() as db:
        s = db.get(JobSource, source)
        s.enabled = False
        s.next_sync_at = utcnow() - timedelta(seconds=1)
    cli.work_once(schedule=True)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(IngestionRun)) == 1


def test_transport_retries_are_persisted_in_run_accounting(source):
    from app.ingestion.service import progress

    with SessionLocal.begin() as db:
        run_id = queue_run(db, source).id
    transport, _, _, _ = transport_sequence(
        http_error(503), Response({"jobs": [raw_job()]}), Response({"job": raw_job()})
    )
    transport.on_retry = lambda: progress(run_id, True)
    process_run(run_id, HimalayasAdapter(transport))
    with SessionLocal() as db:
        run = db.get(IngestionRun, run_id)
        assert run.retried == 1 and run.inserted == 1 and run.status == "completed"


def test_manual_import_cannot_overwrite_integrated_source_or_grant_roles(source, client):
    from app.services.jobs import store_job

    with SessionLocal() as db:
        with pytest.raises(ValueError, match="ingestion pipeline"):
            store_job(db, normalize_himalayas(raw_job(), source).data)
    response = client.post(
        P + "/auth/register",
        json={
            "email": "role-test@example.com",
            "password": "Test-password-827!",
            "is_operator": True,
        },
    )
    assert response.status_code == 422
