from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field
from sqlalchemy import delete, select

from app.api.dependencies import DB, CurrentUser
from app.api.schemas import Schema
from app.core.security import password_hash, utcnow
from app.db.models import AuthSession, RecoveryToken
from app.operations.accounts import delete_account, export_account, recover
from app.services.authentication import throttle

router = APIRouter(prefix="/api/v1/account", tags=["Account privacy and security"])


class RecoveryRequest(Schema):
    email: str = Field(max_length=320)


class RecoveryIn(Schema):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=12, max_length=128)


class DeleteIn(Schema):
    password: str = Field(min_length=1, max_length=128)
    confirmation: str


@router.post("/recovery/request")
def request_recovery(data: RecoveryRequest, request: Request):
    throttle("recovery:" + (request.client.host if request.client else "unknown"))
    return {
        "message": "If recovery delivery is configured and the account is eligible, recovery instructions will be sent.",
        "delivery": "not_configured",
    }


@router.post("/recovery/confirm")
def confirm(data: RecoveryIn, request: Request, db: DB):
    throttle("recover-confirm:" + (request.client.host if request.client else "unknown"))
    return recover(db, data.token, data.password)


@router.get("/sessions")
def sessions(db: DB, user: CurrentUser):
    # Opaque identifiers are not session credentials; no session token digests exposed.
    from app.core.security import digest_token

    return {
        "sessions": [
            {"id": digest_token("session-reference:" + r.token_hash), "expires_at": r.expires_at}
            for r in db.scalars(
                select(AuthSession).where(
                    AuthSession.user_id == user.id, AuthSession.expires_at > utcnow()
                )
            )
        ]
    }


@router.delete("/sessions")
def revoke(db: DB, user: CurrentUser):
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    return {"status": "all_sessions_revoked"}


@router.get("/export")
def export(db: DB, user: CurrentUser):
    return Response(
        export_account(db, user.id),
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=job-search-account.zip",
            "Cache-Control": "no-store",
        },
    )


@router.post("/deletion/confirm")
def deletion(data: DeleteIn, db: DB, user: CurrentUser, response: Response):
    throttle("delete-account:" + user.id)
    if data.confirmation != "DELETE MY ACCOUNT" or not password_hash.verify(
        data.password, user.password_hash
    ):
        raise HTTPException(403, "Password and explicit deletion confirmation required")
    result = delete_account(db, user.id)
    if result["status"] == "deletion_pending":
        response.status_code = 202
    response.delete_cookie("jsi_session")
    return result


class PasswordIn(Schema):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


@router.post("/password")
def change_password(data: PasswordIn, db: DB, user: CurrentUser):
    throttle("password-change:" + user.id)
    if not password_hash.verify(data.current_password, user.password_hash):
        raise HTTPException(403, "Current password required")
    user.password_hash = password_hash.hash(data.new_password)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.execute(delete(RecoveryToken).where(RecoveryToken.user_id == user.id))
    return {"status": "password_changed_all_sessions_revoked"}
