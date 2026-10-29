from fastapi import APIRouter

from app.api.dependencies import DB, CurrentUser
from app.modules.career.schemas import CareerFilters, CareerOut
from app.modules.career.service import overview

router = APIRouter(prefix="/api/v1/career", tags=["Career Intelligence"])


@router.post("/overview", response_model=CareerOut)
def career_overview(data: CareerFilters, db: DB, user: CurrentUser):
    return overview(db, user.id, data)
