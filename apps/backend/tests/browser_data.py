"""Explicit synthetic fixtures for the isolated browser database only."""

import os
from pathlib import Path

from dotenv import dotenv_values

config = dotenv_values(Path(__file__).resolve().parents[3] / ".env")
url = os.environ.get("BROWSER_DATABASE_URL") or config.get("BROWSER_DATABASE_URL")
if not url or not url.rsplit("/", 1)[-1].endswith("_browser"):
    raise RuntimeError(
        "BROWSER_DATABASE_URL must end in _browser; development data is never seeded"
    )
os.environ["DATABASE_URL"] = url

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.api.schemas import JobIn  # noqa: E402
from app.db.models import Base, IngestionRun, JobSource  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.services.jobs import store_job  # noqa: E402

command.upgrade(Config("alembic.ini"), "head")
with engine.begin() as conn:
    tables = ",".join('"' + t.name + '"' for t in Base.metadata.sorted_tables)
    conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
with SessionLocal.begin() as db:
    source = JobSource(name="TEST ONLY — browser fixtures", source_type="manual", enabled=False)
    db.add(source)
    db.flush()
    store_job(
        db,
        JobIn(
            title="TEST ONLY Python Builder",
            employer="TEST ONLY Example Employer",
            description="Synthetic browser test fixture. This is not a real vacancy.",
            source_id=source.id,
            external_id="browser-1",
            location="Kochi",
            work_arrangement="remote",
            employment_type="full_time",
            skills=[{"name": "Python", "kind": "required"}],
        ),
    )
    store_job(
        db,
        JobIn(
            title="TEST ONLY Product Designer",
            employer="TEST ONLY Example Studio",
            description="Synthetic browser test fixture. This is not a real vacancy.",
            source_id=source.id,
            external_id="browser-2",
            location="Pune",
            work_arrangement="hybrid",
            employment_type="contract",
        ),
    )
print("Isolated browser database migrated and seeded with two explicitly synthetic fixtures.")
with SessionLocal.begin() as db:
    status_source = JobSource(
        name="TEST ONLY — failed API source",
        source_type="api",
        adapter_key="himalayas",
        enabled=True,
        operational_status="failed",
        error_code="provider_unavailable",
    )
    db.add(status_source)
    db.flush()
    db.add(
        IngestionRun(
            source_id=status_source.id,
            trigger="test_fixture",
            status="failed",
            max_pages=2,
            error_code="provider_unavailable",
            errors=1,
        )
    )
