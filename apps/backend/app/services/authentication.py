import threading
import time
from collections import defaultdict, deque
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.security import digest_token, new_token, password_hash, utcnow
from app.db.models import AuthSession, User
from app.services.candidates import audit

_dummy_hash = password_hash.hash(new_token())
_attempts: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def throttle(key):
    """Bounded per-process development limiter. Production needs a shared gateway limiter."""
    now = time.monotonic()
    with _lock:
        for old_key in list(_attempts):
            if not _attempts[old_key] or _attempts[old_key][-1] < now - 300:
                del _attempts[old_key]
        entries = _attempts[key]
        while entries and entries[0] < now - 300:
            entries.popleft()
        if len(entries) >= 12:
            raise HTTPException(
                429, "Too many attempts. Try again in five minutes", headers={"Retry-After": "300"}
            )
        entries.append(now)


def start_session(db, user):
    token = new_token()
    db.execute(delete(AuthSession).where(AuthSession.expires_at < utcnow()))
    db.add(
        AuthSession(
            token_hash=digest_token(token),
            user_id=user.id,
            expires_at=utcnow() + timedelta(hours=settings.session_hours),
        )
    )
    db.flush()
    return token


def register(db, data, peer):
    throttle("register:" + peer)
    if not settings.allow_registration:
        raise HTTPException(403, "Registration is disabled")
    email = str(data.email).lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "Unable to register this email")
    user = User(email=email, password_hash=password_hash.hash(data.password))
    db.add(user)
    db.flush()
    audit(db, user.id, "auth.registered", user.id)
    return user, start_session(db, user)


def login(db, data, peer):
    throttle("login:" + peer)
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    valid = password_hash.verify(data.password, user.password_hash if user else _dummy_hash)
    if not user or not valid or user.deletion_pending:
        raise HTTPException(401, "Invalid email or password")
    audit(db, user.id, "auth.login", user.id)
    return user, start_session(db, user)


def authenticate(db, token):
    if not token:
        raise HTTPException(401, "Sign in to continue")
    session = db.get(AuthSession, digest_token(token))
    if session is None or session.expires_at <= utcnow():
        raise HTTPException(401, "Session expired. Sign in again")
    user = db.get(User, session.user_id)
    if user is None or user.deletion_pending:
        raise HTTPException(401, "Session is no longer valid")
    return user


def logout(db, token, user_id):
    db.execute(delete(AuthSession).where(AuthSession.token_hash == digest_token(token)))
    audit(db, user_id, "auth.logout", user_id)
