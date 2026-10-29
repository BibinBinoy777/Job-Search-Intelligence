# ruff: noqa: E402
"""Additional browser fixtures only, with scoped cleanup so old journeys still see two jobs."""

import os
import sys
from pathlib import Path

from dotenv import dotenv_values

env = dotenv_values(Path(__file__).resolve().parents[3] / ".env")
url = os.environ.get("BROWSER_DATABASE_URL") or env.get("BROWSER_DATABASE_URL")
if not url or not url.rsplit("/", 1)[-1].endswith("_browser"):
    raise RuntimeError("Career browser fixtures require an isolated _browser database")
os.environ["DATABASE_URL"] = url


from sqlalchemy import delete, select

from app.db.models import IngestionRecord, IngestionRun, Job, JobSource, User
from app.db.session import SessionLocal
from app.ingestion.control import queue_run
from app.ingestion.service import process_run
from app.modules.automation.worker import background_once
from app.modules.sources.contracts import SourcePage
from tests.test_discovery import AdapterFixture, raw_job

NAME = "TEST ONLY — automation browser fixtures"
action = sys.argv[1]
if action == "operator":
    with SessionLocal.begin() as db:
        user = db.scalar(
            select(User)
            .where(User.email.like("automation-%@example.com"))
            .order_by(User.created_at.desc())
            .limit(1)
        )
        assert user
        user.is_operator = True
    print("Isolated browser automation account promoted for operator UI verification.")
elif action == "tick":
    print(background_once())
elif action == "ingest":
    with SessionLocal.begin() as db:
        source = db.scalar(select(JobSource).where(JobSource.name == NAME))
        if not source:
            source = JobSource(
                name=NAME, source_type="api", adapter_key="himalayas", enabled=True, page_limit=1
            )
            db.add(source)
            db.flush()
        run = queue_run(db, source.id)
        key = run.id
    assert process_run(
        key,
        AdapterFixture(
            [
                SourcePage(
                    [raw_job(slug="automation-browser", title="TEST ONLY Automation Browser Job")],
                    None,
                )
            ]
        ),
    )
    print("Isolated synthetic ingestion completed.")
elif action == "clean":
    with SessionLocal.begin() as db:
        source = db.scalar(select(JobSource).where(JobSource.name == NAME))
        if source:
            run_ids = select(IngestionRun.id).where(IngestionRun.source_id == source.id)
            db.execute(delete(IngestionRecord).where(IngestionRecord.run_id.in_(run_ids)))
            db.execute(delete(IngestionRun).where(IngestionRun.source_id == source.id))
            db.execute(delete(Job).where(Job.source_id == source.id))
            db.delete(source)
    print("Scoped isolated automation fixtures removed.")
else:
    raise RuntimeError("Choose ingest, tick, or clean")
