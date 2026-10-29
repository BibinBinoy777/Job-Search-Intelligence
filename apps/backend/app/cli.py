"""Trusted operator import of candidate-provided or permitted-source job JSON.

No bundled vacancies, crawling, scheduler, invented source URLs or hidden seed.
"""

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.api.schemas import JobIn
from app.db.models import JobSource
from app.db.session import SessionLocal
from app.services.jobs import store_job


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="JSON array of real canonical job records")
    parser.add_argument("--source-name", required=True)
    parser.add_argument(
        "--source-type", choices=["manual", "api", "feed", "employer"], default="manual"
    )
    args = parser.parse_args()
    data = json.loads(args.file.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        parser.error("Expected a JSON array")
    with SessionLocal.begin() as db:
        source = db.scalar(select(JobSource).where(JobSource.name == args.source_name))
        if source is None:
            source = JobSource(name=args.source_name, source_type=args.source_type, enabled=False)
            db.add(source)
            db.flush()
        for raw in data:
            canonical = JobIn.model_validate({**raw, "source_id": source.id})
            store_job(db, canonical)
    print(f"Imported {len(data)} supplied records. Source integration remains disabled.")


if __name__ == "__main__":
    main()
