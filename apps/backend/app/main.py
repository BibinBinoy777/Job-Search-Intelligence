import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException

from app.api.automation import router as automation_router
from app.api.career import router as career_router
from app.api.ingestion import router as ingestion_router
from app.api.matching import router as matching_router
from app.api.resumes import router as resumes_router
from app.api.routes import router
from app.api.search import router as search_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import engine
from app.modules.resumes.body_limit import ResumeBodyLimit

configure_logging()
logger = logging.getLogger("jsi")
app = FastAPI(
    title="Job Search Intelligence",
    version="0.7.0",
    description="Phase 7: evidence-backed career gaps, roles, paths and learning with scoped market statistics; existing discovery, matching and private resume review. No automated applications.",
)
app.add_middleware(ResumeBodyLimit)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-Resume-Filename"],
)


@app.middleware("http")
async def boundary(request: Request, call_next):
    request_id = str(uuid4())
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin and origin not in settings.allowed_origins:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {"code": "origin_rejected", "message": "Request origin is not allowed"}
                },
            )
        # Non-browser CLI clients may omit Origin. Browser fetch metadata closes
        # the cross-site omission case; SameSite=Lax also protects the cookie.
        if not origin and request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "origin_rejected",
                        "message": "Cross-site writes are not allowed",
                    }
                },
            )
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": f"http_{exc.status_code}", "message": str(exc.detail)}},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
@app.exception_handler(ValidationError)
async def validation_error(request, exc):
    fields = [{"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Check the highlighted fields",
                "fields": fields,
            }
        },
    )


@app.exception_handler(IntegrityError)
@app.exception_handler(StaleDataError)
async def conflict_error(request, exc):
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "code": "conflict",
                "message": "Record conflicts with existing data. Refresh and try again",
            }
        },
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    logger.error("database_operation_failed type=%s", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "database_unavailable",
                "message": "Database temporarily unavailable. Try again later",
            }
        },
    )


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    logger.error("unhandled_request_error type=%s", type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "Unable to complete request"}},
    )


@app.get("/api/v1/health/live", tags=["System"])
def live():
    return {"status": "ok"}


@app.get("/api/v1/health/ready", tags=["System"])
def ready():
    try:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            if revision != "0006_automation":
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": {
                            "code": "schema_not_ready",
                            "message": "Database migrations are required",
                        }
                    },
                )
            connection.execute(text("SELECT id FROM users LIMIT 1"))
        return {"status": "ready", "database": "reachable", "migration": revision}
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "dependency_unavailable",
                    "message": "Database is unavailable or requires migration",
                }
            },
        )


app.include_router(resumes_router)
app.include_router(career_router)
app.include_router(automation_router)
app.include_router(search_router)
app.include_router(router)
app.include_router(ingestion_router)
app.include_router(matching_router)
