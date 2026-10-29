import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

env = dotenv_values(Path(__file__).resolve().parents[3] / ".env")
test_url = os.environ.get("TEST_DATABASE_URL") or env.get("TEST_DATABASE_URL")
if not test_url or not test_url.rsplit("/", 1)[-1].endswith("_test"):
    raise RuntimeError("TEST_DATABASE_URL must point to a disposable database ending in _test")
os.environ["DATABASE_URL"] = test_url
os.environ["APP_ENV"] = "test"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.api.schemas import JobIn  # noqa: E402
from app.db.models import Base, JobSource  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.authentication import _attempts  # noqa: E402
from app.services.jobs import store_job  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    command.check(config)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(migrated_database):
    names = ",".join('"' + t.name + '"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    _attempts.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def signup(client, email="candidate@example.com", profile=True):
    result = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "Test-password-827!"}
    )
    assert result.status_code == 201, result.text
    if profile:
        result = client.post("/api/v1/profile", json={"name": "Test Candidate"})
        assert result.status_code == 201, result.text
    return client


@pytest.fixture
def candidate(client):
    return signup(client)


@pytest.fixture
def other():
    with TestClient(app) as client:
        yield signup(client, "other@example.com")


@pytest.fixture
def seeded_jobs():
    with SessionLocal.begin() as db:
        source = JobSource(name="TEST ONLY — isolated source", source_type="manual")
        db.add(source)
        db.flush()
        first = store_job(
            db,
            JobIn(
                title="TEST ONLY Python Developer",
                employer="TEST ONLY Employer",
                description="Synthetic API test fixture. Python FastAPI.",
                source_id=source.id,
                external_id="fixture-a",
                location="Kochi",
                work_arrangement="remote",
                employment_type="full_time",
                skills=[{"name": "Python", "kind": "required"}],
            ),
        )
        second = store_job(
            db,
            JobIn(
                title="TEST ONLY Designer",
                employer="TEST ONLY Studio",
                description="Synthetic API test fixture.",
                source_id=source.id,
                external_id="fixture-b",
                location="Pune",
                work_arrangement="hybrid",
                employment_type="contract",
            ),
        )
        return first.id, second.id, source.id
