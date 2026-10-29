from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.dependencies import DB, CurrentUser, PageSize
from app.api.schemas import Page
from app.modules.search import service
from app.modules.search.schemas import (
    CompareIn,
    ComparisonOut,
    SavedSearchIn,
    SavedSearchOut,
    SavedSearchPatch,
    SuggestionsOut,
)

router = APIRouter(prefix="/api/v1", tags=["Discovery"])


@router.get("/jobs/suggestions", response_model=SuggestionsOut)
def suggestions(
    db: DB,
    user: CurrentUser,
    q: Annotated[str, Query(max_length=100)] = "",
    limit: Annotated[int, Query(ge=1, le=12)] = 8,
):
    return service.suggestions(db, q, limit)


@router.post("/jobs/compare", response_model=ComparisonOut)
def compare(data: CompareIn, db: DB, user: CurrentUser):
    return service.compare(db, user.id, data)


@router.get("/saved-searches", response_model=Page[SavedSearchOut])
def saved_searches(
    db: DB,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    page_size: PageSize = 20,
):
    return service.saved_list(db, user.id, page, page_size)


@router.post("/saved-searches", response_model=SavedSearchOut, status_code=201)
def save_search(data: SavedSearchIn, db: DB, user: CurrentUser):
    return service.save_search(db, user.id, data)


@router.patch("/saved-searches/{search_id}", response_model=SavedSearchOut)
def update_search(search_id: UUID, data: SavedSearchPatch, db: DB, user: CurrentUser):
    return service.update_search(db, user.id, str(search_id), data)


@router.post("/saved-searches/{search_id}/use", response_model=SavedSearchOut)
def use_search(search_id: UUID, db: DB, user: CurrentUser):
    return service.use_search(db, user.id, str(search_id))


@router.delete("/saved-searches/{search_id}", status_code=204)
def delete_search(search_id: UUID, db: DB, user: CurrentUser):
    db.delete(service.owned_search(db, user.id, str(search_id)))
