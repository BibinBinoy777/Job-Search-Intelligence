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

from sqlalchemy import delete, select  # noqa: E402

from app.api.schemas import JobIn  # noqa: E402
from app.db.models import Job, JobSource  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.jobs import store_job  # noqa: E402

NAME = "TEST ONLY — career browser fixtures"
with SessionLocal.begin() as db:
    source = db.scalar(select(JobSource).where(JobSource.name == NAME))
    if sys.argv[1:] == ["clean"]:
        if source:
            assert source.enabled is False and source.source_type == "manual"
            db.execute(delete(Job).where(Job.source_id == source.id))
            db.delete(source)
        print("Scoped isolated career browser fixtures removed.")
    elif sys.argv[1:] == ["seed"]:
        if source:
            raise RuntimeError(
                "Previous career fixtures remain; clean the isolated fixture source first"
            )
        source = JobSource(name=NAME, source_type="manual", enabled=False)
        db.add(source)
        db.flush()
        for key, title, body, location in [
            (
                "analyst",
                "TEST ONLY Career Data Analyst",
                "Required skills\nPython and SQL\nPreferred skills\nAWS",
                "Kochi",
            ),
            (
                "api",
                "TEST ONLY Career API Engineer",
                "Required skills\nPython and Docker\nRequired qualifications\nBachelor degree or equivalent\nCertification required\n2 years experience",
                "Pune",
            ),
        ]:
            store_job(
                db,
                JobIn(
                    title=title,
                    employer="TEST ONLY Career Employer",
                    description=body,
                    source_id=source.id,
                    external_id=key,
                    location=location,
                ),
            )
        print("Two explicitly synthetic career browser records seeded in _browser only.")
    else:
        raise RuntimeError("Choose seed or clean")
