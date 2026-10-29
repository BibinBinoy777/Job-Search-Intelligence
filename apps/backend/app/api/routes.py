from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select

from app.api import schemas as s
from app.api.dependencies import DB, CurrentUser, PageNumber, PageSize
from app.core.config import settings
from app.db.models import JobSource
from app.db.repositories import current_profile, job_by_id, owned_application, paginate
from app.modules.search.schemas import SearchPage, SearchParams
from app.services import applications, authentication, candidates, jobs
from app.services.overview import overview

router = APIRouter(prefix="/api/v1")


def set_cookie(response, token):
    response.set_cookie(
        "jsi_session",
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_hours * 3600,
        path="/",
    )


@router.post("/auth/register", response_model=s.UserOut, status_code=201, tags=["Authentication"])
def register(data: s.Credentials, request: Request, response: Response, db: DB):
    user, token = authentication.register(
        db, data, request.client.host if request.client else "unknown"
    )
    set_cookie(response, token)
    return user


@router.post("/auth/login", response_model=s.UserOut, tags=["Authentication"])
def login(data: s.Credentials, request: Request, response: Response, db: DB):
    user, token = authentication.login(
        db, data, request.client.host if request.client else "unknown"
    )
    set_cookie(response, token)
    return user


@router.post("/auth/logout", status_code=204, tags=["Authentication"])
def logout(request: Request, response: Response, db: DB, user: CurrentUser):
    authentication.logout(db, request.cookies["jsi_session"], user.id)
    response.delete_cookie("jsi_session", path="/")


@router.get("/auth/me", response_model=s.UserOut, tags=["Authentication"])
def me(user: CurrentUser):
    return user


@router.get("/overview", tags=["Overview"])
def get_overview(db: DB, user: CurrentUser):
    return overview(db, user.id)


@router.get("/profile", response_model=s.ProfileOut, tags=["Profile"])
def get_profile(db: DB, user: CurrentUser):
    return current_profile(db, user.id)


@router.post("/profile", response_model=s.ProfileOut, status_code=201, tags=["Profile"])
def create_profile(data: s.ProfileEdit, db: DB, user: CurrentUser):
    return candidates.create_profile(db, user.id, data)


@router.patch("/profile", response_model=s.ProfileOut, tags=["Profile"])
def edit_profile(data: s.ProfileEdit, db: DB, user: CurrentUser):
    return candidates.update_profile(db, user.id, data)


@router.get("/profile/skills", response_model=list[s.SkillOut], tags=["Profile"])
def list_skills(db: DB, user: CurrentUser):
    return current_profile(db, user.id).skills


@router.post("/profile/skills", response_model=s.SkillOut, tags=["Profile"])
def add_skill(data: s.SkillIn, db: DB, user: CurrentUser):
    return candidates.add_skill(db, user.id, data)


@router.delete("/profile/skills/{item_id}", status_code=204, tags=["Profile"])
def remove_skill(item_id: UUID, db: DB, user: CurrentUser):
    candidates.delete_child(db, user.id, "skills", str(item_id))


@router.get("/profile/experience", response_model=list[s.ExperienceOut], tags=["Profile"])
def list_experience(db: DB, user: CurrentUser):
    return current_profile(db, user.id).experience


@router.post(
    "/profile/experience", response_model=s.ExperienceOut, status_code=201, tags=["Profile"]
)
def add_experience(data: s.ExperienceIn, db: DB, user: CurrentUser):
    return candidates.save_child(db, user.id, "experience", data)


@router.put("/profile/experience/{item_id}", response_model=s.ExperienceOut, tags=["Profile"])
def edit_experience(item_id: UUID, data: s.ExperienceIn, db: DB, user: CurrentUser):
    return candidates.save_child(db, user.id, "experience", data, str(item_id))


@router.delete("/profile/experience/{item_id}", status_code=204, tags=["Profile"])
def remove_experience(item_id: UUID, db: DB, user: CurrentUser):
    candidates.delete_child(db, user.id, "experience", str(item_id))


@router.get("/profile/education", response_model=list[s.EducationOut], tags=["Profile"])
def list_education(db: DB, user: CurrentUser):
    return current_profile(db, user.id).education


@router.post("/profile/education", response_model=s.EducationOut, status_code=201, tags=["Profile"])
def add_education(data: s.EducationIn, db: DB, user: CurrentUser):
    return candidates.save_child(db, user.id, "education", data)


@router.put("/profile/education/{item_id}", response_model=s.EducationOut, tags=["Profile"])
def edit_education(item_id: UUID, data: s.EducationIn, db: DB, user: CurrentUser):
    return candidates.save_child(db, user.id, "education", data, str(item_id))


@router.delete("/profile/education/{item_id}", status_code=204, tags=["Profile"])
def remove_education(item_id: UUID, db: DB, user: CurrentUser):
    candidates.delete_child(db, user.id, "education", str(item_id))


@router.get("/profile/preferences", response_model=s.PreferencesIn, tags=["Profile"])
def get_preferences(db: DB, user: CurrentUser):
    return current_profile(db, user.id).preferences or s.PreferencesIn()


@router.patch("/profile/preferences", response_model=s.PreferencesIn, tags=["Profile"])
def edit_preferences(data: s.PreferencesIn, db: DB, user: CurrentUser):
    return candidates.update_preferences(db, user.id, data)


@router.get("/jobs", response_model=SearchPage, tags=["Jobs"])
def list_jobs(db: DB, user: CurrentUser, params: Annotated[SearchParams, Query()]):
    return jobs.list_jobs(db, user.id, params)


@router.get("/jobs/{job_id}", response_model=s.JobOut, tags=["Jobs"])
def get_job(job_id: UUID, db: DB, user: CurrentUser):
    return jobs.present_job(db, user.id, job_by_id(db, str(job_id)))


@router.get("/sources", response_model=s.Page[s.SourceOut], tags=["Jobs"])
def sources(db: DB, user: CurrentUser, page: PageNumber = 1, page_size: PageSize = 20):
    return paginate(db, select(JobSource).order_by(JobSource.name, JobSource.id), page, page_size)


@router.put("/jobs/{job_id}/save", tags=["Saved jobs"])
def save_job(job_id: UUID, db: DB, user: CurrentUser):
    return jobs.save_job(db, user.id, str(job_id))


@router.delete("/jobs/{job_id}/save", status_code=204, tags=["Saved jobs"])
def unsave_job(job_id: UUID, db: DB, user: CurrentUser):
    jobs.unsave_job(db, user.id, str(job_id))


@router.get("/saved-jobs", response_model=s.Page[s.SavedOut], tags=["Saved jobs"])
def saved_jobs(db: DB, user: CurrentUser, page: PageNumber = 1, page_size: PageSize = 20):
    return jobs.saved_jobs(db, user.id, page, page_size)


@router.get("/applications", response_model=s.Page[s.ApplicationOut], tags=["Applications"])
def list_applications(db: DB, user: CurrentUser, page: PageNumber = 1, page_size: PageSize = 20):
    return applications.list_applications(db, user.id, page, page_size)


@router.post(
    "/applications", response_model=s.ApplicationOut, status_code=201, tags=["Applications"]
)
def create_application(data: s.ApplicationIn, db: DB, user: CurrentUser):
    return applications.create_application(db, user.id, data)


@router.get(
    "/applications/{application_id}", response_model=s.ApplicationOut, tags=["Applications"]
)
def get_application(application_id: UUID, db: DB, user: CurrentUser):
    return owned_application(db, user.id, str(application_id))


@router.patch(
    "/applications/{application_id}", response_model=s.ApplicationOut, tags=["Applications"]
)
def update_application(application_id: UUID, data: s.ApplicationPatch, db: DB, user: CurrentUser):
    return applications.update_application(db, user.id, str(application_id), data)


@router.get(
    "/applications/{application_id}/events",
    response_model=s.Page[s.EventOut],
    tags=["Applications"],
)
def events(
    application_id: UUID, db: DB, user: CurrentUser, page: PageNumber = 1, page_size: PageSize = 20
):
    return applications.application_events(db, user.id, str(application_id), page, page_size)
