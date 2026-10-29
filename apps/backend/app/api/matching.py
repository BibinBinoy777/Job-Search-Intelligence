from uuid import UUID

from fastapi import APIRouter, Query

from app.api.dependencies import DB, CurrentUser, PageNumber, PageSize
from app.api.schemas import EmploymentType, Page, WorkMode
from app.modules.matching import service
from app.modules.matching.schemas import EligibilityState, MatchOut, PairOut, RefreshIn, RefreshOut

router = APIRouter(prefix="/api/v1", tags=["Matching"])


@router.get("/matches", response_model=Page[MatchOut])
def matches(
    db: DB,
    user: CurrentUser,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    minimum_score: float | None = Query(default=None, ge=0, le=100),
    eligibility: EligibilityState | None = None,
    location: str | None = Query(default=None, max_length=250),
    employment_type: EmploymentType | None = None,
    work_arrangement: WorkMode | None = None,
    source_id: UUID | None = None,
    required_coverage: float | None = Query(default=None, ge=0, le=1),
    include_stale: bool = False,
):
    return service.recommendations(
        db,
        user.id,
        page,
        page_size,
        minimum_score,
        eligibility,
        location,
        employment_type,
        work_arrangement,
        str(source_id) if source_id else None,
        required_coverage,
        include_stale,
    )


@router.post("/matches/refresh", response_model=RefreshOut)
def refresh(data: RefreshIn, db: DB, user: CurrentUser):
    return service.refresh(db, user.id, data)


@router.get("/matches/{job_id}", response_model=PairOut)
@router.get("/jobs/{job_id}/match", response_model=PairOut)
def pair(job_id: UUID, db: DB, user: CurrentUser):
    return service.pair(db, user.id, str(job_id))


@router.get("/matching/status")
def status(db: DB, user: CurrentUser):
    result = service.status(db, user.id)
    result["last_refresh"] = (
        RefreshOut.model_validate(result["last_refresh"]) if result["last_refresh"] else None
    )
    return result
