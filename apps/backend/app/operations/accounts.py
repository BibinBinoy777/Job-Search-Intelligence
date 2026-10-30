"""Owned account operations; no recovery credentials in HTTP responses or logs."""

import io
import json
import zipfile
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import Text, cast, delete, func, select

from app.core.config import settings
from app.core.security import digest_token, new_token, password_hash, utcnow
from app.db.models import AuthSession, Base, Profile, RecoveryToken, Resume, ResumeVersion, User
from app.modules.resumes.storage import PrivateStorage


def issue_local_recovery(db, email):
    if settings.app_env not in {"development", "test"}:
        raise HTTPException(403, "Local recovery issuance is disabled")
    user = db.scalar(select(User).where(User.email == email.lower()).with_for_update())
    if not user or user.deletion_pending:
        raise HTTPException(404, "Account unavailable")
    db.execute(delete(RecoveryToken).where(RecoveryToken.user_id == user.id))
    token = new_token()
    db.add(
        RecoveryToken(
            user_id=user.id,
            token_hash=digest_token(token),
            expires_at=utcnow() + timedelta(minutes=20),
        )
    )
    return token


def recover(db, token, password):
    row = db.scalar(
        select(RecoveryToken)
        .where(RecoveryToken.token_hash == digest_token(token))
        .with_for_update()
    )
    if not row or row.expires_at <= utcnow():
        raise HTTPException(422, "Recovery credential invalid or expired")
    user = db.scalar(select(User).where(User.id == row.user_id).with_for_update())
    if not user or user.deletion_pending:
        raise HTTPException(422, "Recovery credential invalid or expired")
    user.password_hash = password_hash.hash(password)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.execute(delete(RecoveryToken).where(RecoveryToken.user_id == user.id))
    return {"status": "password_changed_sessions_revoked"}


def delete_account(db, user_id):
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not user:
        return {"status": "deleted"}
    user.deletion_pending = True
    db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    db.execute(delete(RecoveryToken).where(RecoveryToken.user_id == user_id))
    db.commit()  # Durable access barrier before filesystem cleanup.
    profile = db.scalar(select(Profile).where(Profile.user_id == user_id))
    if profile:
        refs = db.scalars(
            select(ResumeVersion.storage_ref).join(Resume).where(Resume.profile_id == profile.id)
        ).all()
        try:
            storage = PrivateStorage()
            for ref in refs:
                storage.delete(ref)
        except (OSError, ValueError):
            return {"status": "deletion_pending"}
    # Database cascades remove candidate-owned rows; global vacancies/history remain.
    db.delete(user)
    db.flush()
    return {"status": "deleted"}


def export_account(db, user_id):
    allow = {
        "users",
        "candidate_profiles",
        "candidate_skills",
        "candidate_education",
        "candidate_experience",
        "candidate_preferences",
        "saved_jobs",
        "saved_searches",
        "applications",
        "application_events",
        "match_results",
        "matching_refreshes",
        "resumes",
        "resume_versions",
        "resume_extractions",
        "resume_proposals",
        "resume_confirmations",
        "alert_subscriptions",
        "notification_preferences",
        "notifications",
        "notification_outbox",
        "notification_attempts",
        "application_reminders",
    }
    identifiers = {"users": {user_id}}
    rows = {}
    versions = []
    encoded_size = 0
    for table in Base.metadata.sorted_tables:
        if table.name not in allow:
            continue
        condition = None
        if table.name == "users":
            condition = table.c.id == user_id
        else:
            from sqlalchemy import or_

            conditions = [
                fk.parent.in_(identifiers[fk.column.table.name])
                for fk in table.foreign_keys
                if fk.column.table.name in identifiers and identifiers[fk.column.table.name]
            ]
            if conditions:
                condition = or_(*conditions)
        if condition is None:
            continue
        sizes = db.scalars(
            select(func.octet_length(cast(func.row_to_json(table.table_valued()), Text)))
            .where(condition)
            .limit(5001)
        ).all()
        encoded_size += sum(sizes)
        if len(sizes) > 5000 or encoded_size > 64 * 1024 * 1024:
            raise HTTPException(
                413, "Export exceeds local size/row limit; request operator assistance"
            )
        records = db.execute(select(table).where(condition).limit(5001)).mappings().all()
        if len(records) > 5000:
            raise HTTPException(413, "Export exceeds local row limit; request operator assistance")
        clean = []
        for record in records:
            value = dict(record)
            for secret in ["password_hash", "token_hash"]:
                value.pop(secret, None)
            clean.append(value)
        rows[table.name] = clean
        if "id" in table.c:
            identifiers[table.name] = {r["id"] for r in records}
        if table.name == "resume_versions":
            versions = clean
    stream = io.BytesIO()
    total = 0
    storage = PrivateStorage()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        body = json.dumps(
            {
                "format": "jsi-candidate-export-1",
                "exported_at": utcnow().isoformat(),
                "records": rows,
            },
            default=str,
        ).encode()
        total += len(body)
        archive.writestr("account.json", body)
        for version in versions:
            content = storage.read(version["storage_ref"])
            total += len(content)
            if total > 100 * 1024 * 1024:
                raise HTTPException(413, "Export exceeds 100 MiB limit")
            archive.writestr("resumes/" + version["id"] + "." + version["detected_type"], content)
    return stream.getvalue()
