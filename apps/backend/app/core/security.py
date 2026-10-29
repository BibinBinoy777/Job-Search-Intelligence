import hashlib
import secrets
from datetime import datetime, timezone

from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_token() -> str:
    return secrets.token_urlsafe(48)


def digest_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
