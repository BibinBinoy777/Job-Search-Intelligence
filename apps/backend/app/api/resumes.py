from typing import Annotated
from urllib.parse import quote, unquote
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Response
from sqlalchemy import select

from app.api.dependencies import DB, CurrentUser
from app.core.config import settings
from app.db.models import ResumeExtraction, ResumeVersion
from app.modules.resumes import review, service
from app.modules.resumes.schemas import (
    ConfirmIn,
    ConfirmOut,
    DeleteOut,
    ExtractionOut,
    PreviewOut,
    ProcessIn,
    ResumeOut,
    ReviewIn,
)
from app.modules.resumes.storage import PrivateStorage
from app.modules.resumes.validation import MIMES

router = APIRouter(prefix="/api/v1", tags=["Resume Intelligence"])


@router.get("/resumes/config")
def config(user: CurrentUser):
    return {
        "max_bytes": settings.resume_max_bytes,
        "formats": ["pdf", "docx"],
        "max_resumes": 10,
        "max_versions": 20,
        "malware_scanning": "not_configured",
        "external_ai": False,
        "ocr": False,
    }


@router.get("/resumes", response_model=list[ResumeOut])
def library(db: DB, user: CurrentUser):
    return service.library(db, user.id)


async def read_upload(request):
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > settings.resume_max_bytes:
            raise HTTPException(413, "Resume exceeds the configured upload size")
        content.extend(chunk)
    return bytes(content)


@router.post("/resumes", response_model=ResumeOut, status_code=201)
async def upload(
    request: Request,
    db: DB,
    user: CurrentUser,
    filename: Annotated[str, Header(alias="X-Resume-Filename", min_length=1, max_length=2160)],
):
    return service.upload(
        db,
        user.id,
        unquote(filename),
        request.headers.get("content-type", ""),
        await read_upload(request),
    )


@router.post("/resumes/{resume_id}/versions", response_model=ResumeOut, status_code=201)
async def upload_version(
    resume_id: UUID,
    request: Request,
    db: DB,
    user: CurrentUser,
    filename: Annotated[str, Header(alias="X-Resume-Filename", min_length=1, max_length=2160)],
):
    service.owned_resume(db, user.id, str(resume_id))
    return service.upload(
        db,
        user.id,
        unquote(filename),
        request.headers.get("content-type", ""),
        await read_upload(request),
        str(resume_id),
    )


@router.get("/resumes/{resume_id}", response_model=ResumeOut)
def metadata(resume_id: UUID, db: DB, user: CurrentUser):
    return service.present_resume(
        db, service.owned_resume(db, user.id, str(resume_id), allow_pending=True)
    )


@router.get("/resumes/{resume_id}/versions/{version_id}/download")
def download(resume_id: UUID, version_id: UUID, db: DB, user: CurrentUser):
    version = service.version_for(db, user.id, str(resume_id), str(version_id))
    try:
        content = PrivateStorage().read(version.storage_ref)
    except (OSError, ValueError):
        raise HTTPException(404, "Private document is not available") from None
    return Response(
        content,
        media_type=MIMES[version.detected_type],
        headers={
            "Content-Disposition": f"attachment; filename=resume.{version.detected_type}; filename*=UTF-8''{quote(version.filename, safe='')}",
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


@router.post("/resumes/{resume_id}/process", response_model=ExtractionOut)
def process(resume_id: UUID, data: ProcessIn, db: DB, user: CurrentUser):
    return service.process(db, user.id, str(resume_id), str(data.version_id))


@router.get("/resumes/{resume_id}/extractions", response_model=list[ExtractionOut])
def extractions(resume_id: UUID, db: DB, user: CurrentUser):
    service.owned_resume(db, user.id, str(resume_id))
    runs = db.scalars(
        select(ResumeExtraction)
        .join(ResumeVersion)
        .where(ResumeVersion.resume_id == str(resume_id))
        .order_by(ResumeExtraction.started_at.desc())
        .limit(20)
    ).all()
    return [service.present_extraction(db, run) for run in runs]


@router.get("/extractions/{extraction_id}", response_model=ExtractionOut)
def extraction(extraction_id: UUID, db: DB, user: CurrentUser):
    return service.present_extraction(db, service.owned_extraction(db, user.id, str(extraction_id)))


@router.post("/extractions/{extraction_id}/review", response_model=ExtractionOut)
def review_items(extraction_id: UUID, data: ReviewIn, db: DB, user: CurrentUser):
    return review.review(db, user.id, str(extraction_id), data)


@router.get("/extractions/{extraction_id}/preview", response_model=PreviewOut)
def preview(extraction_id: UUID, db: DB, user: CurrentUser):
    return review.preview(db, user.id, str(extraction_id))


@router.post("/extractions/{extraction_id}/confirm", response_model=ConfirmOut)
def confirm(extraction_id: UUID, data: ConfirmIn, db: DB, user: CurrentUser):
    return review.confirm(db, user.id, str(extraction_id), data)


@router.delete("/resumes/{resume_id}", response_model=DeleteOut)
def delete(resume_id: UUID, response: Response, db: DB, user: CurrentUser):
    result = service.delete(db, user.id, str(resume_id))
    if result["status"] == "deletion_pending":
        response.status_code = 202
    return result
