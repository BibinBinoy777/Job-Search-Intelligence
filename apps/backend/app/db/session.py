import logging

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url, pool_pre_ping=True, connect_args={"connect_timeout": 3}
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db(request: Request):
    with SessionLocal() as session:
        try:
            if request.url.path == "/api/v1/career/overview":
                # Set before authentication's first query: all career counts,
                # records and evidence must share one point-in-time DB snapshot.
                session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            yield session
            session.commit()
        except Exception:
            session.rollback()
            for cleanup in session.info.pop("resume_rollback_cleanup", []):
                try:
                    cleanup()
                except OSError:
                    logging.getLogger(__name__).error(
                        "Private resume rollback cleanup requires retry"
                    )
            raise
