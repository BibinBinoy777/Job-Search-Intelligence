from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.api.dependencies import DB, CurrentUser, PageNumber, PageSize
from app.api.schemas import Page, Schema, SourceOut
from app.db.models import DuplicateCandidate, IngestionRecord, IngestionRun, Job, JobSource
from app.ingestion.control import get_run, list_runs, queue_run, run_records
from app.ingestion.freshness import visible_job_condition

router = APIRouter(prefix="/api/v1", tags=["Ingestion"])


class RunOut(Schema):
    id: str
    source_id: str
    source: SourceOut
    trigger: str
    status: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    heartbeat_at: datetime | None
    max_pages: int
    pages: int
    fetched: int
    accepted: int
    inserted: int
    updated: int
    unchanged: int
    duplicates: int
    rejected: int
    skipped: int
    retried: int
    errors: int
    error_code: str | None
    attempt_number: int = 1
    root_run_id: str | None = None
    retry_at: datetime | None = None
    retry_spawned: bool = False
    has_more: bool = False
    reconciled: bool | None = None


class RecordOut(Schema):
    id: str
    page_number: int
    record_number: int
    job_id: str | None
    outcome: str
    error_code: str | None


class SyncIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: UUID
    resume_run_id: UUID | None = None


def present_run(db, run):
    result = RunOut.model_validate(run)
    result.has_more = bool(run.next_cursor)
    if run.status in {"queued", "running"}:
        return result
    counts = dict(
        db.execute(
            select(IngestionRecord.outcome, func.count())
            .where(IngestionRecord.run_id == run.id)
            .group_by(IngestionRecord.outcome)
        ).all()
    )
    result.reconciled = sum(counts.values()) == run.fetched and all(
        counts.get(k, 0) == getattr(run, "duplicates" if k == "duplicate" else k)
        for k in ["inserted", "updated", "unchanged", "duplicate", "rejected", "skipped"]
    )
    return result


@router.post("/ingestion/sync", response_model=RunOut, status_code=202)
def sync(data: SyncIn, db: DB, user: CurrentUser):
    if not user.is_operator:
        raise HTTPException(403, "Operator access is required to trigger synchronization")
    run = queue_run(
        db,
        str(data.source_id),
        user_id=user.id,
        resume_run_id=str(data.resume_run_id) if data.resume_run_id else None,
    )
    return present_run(db, run)


@router.get("/ingestion/runs", response_model=Page[RunOut])
def runs(
    db: DB,
    user: CurrentUser,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    source_id: UUID | None = None,
):
    result = list_runs(db, page, page_size, str(source_id) if source_id else None)
    result["items"] = [present_run(db, run) for run in result["items"]]
    return result


@router.get("/ingestion/runs/{run_id}", response_model=RunOut)
def run(run_id: UUID, db: DB, user: CurrentUser):
    return present_run(db, get_run(db, str(run_id)))


@router.get("/ingestion/runs/{run_id}/records", response_model=Page[RecordOut])
def records(
    run_id: UUID, db: DB, user: CurrentUser, page: PageNumber = 1, page_size: PageSize = 20
):
    return run_records(db, str(run_id), page, page_size)


@router.get("/sources/status")
@router.get("/ingestion/status")
def status(db: DB, user: CurrentUser):
    sources = db.scalars(select(JobSource).order_by(JobSource.name)).all()
    items = []
    for source in sources:
        latest = db.scalar(
            select(IngestionRun)
            .where(IngestionRun.source_id == source.id)
            .order_by(IngestionRun.created_at.desc())
            .limit(1)
        )
        items.append(
            {
                "source": SourceOut.model_validate(source),
                "latest_run": present_run(db, latest) if latest else None,
                "stored_jobs": db.scalar(
                    select(func.count()).select_from(Job).where(Job.source_id == source.id)
                ),
                "available_jobs": db.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(Job.source_id == source.id, visible_job_condition())
                ),
            }
        )
    return {
        "sources": items,
        "can_sync": user.is_operator,
        "worker_required": True,
        "probable_duplicate_pairs": db.scalar(select(func.count()).select_from(DuplicateCandidate)),
    }
