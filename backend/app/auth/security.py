"""Password hashing and JWT issuance/verification (DOC 2 §6, US-030).
Deliberately minimal for the dashboard backend's first milestone — a single
operator account rather than a full multi-user system, matching "solo quant
developer" as the primary user (DOC 1 §1.4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from jose import JWTError, jwt

DEFAULT_ALGORITHM = "HS256"
DEFAULT_ACCESS_TOKEN_MINUTES = 30  # DOC 1 US-030: 30-minute session


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())



class TokenError(Exception):
    pass


def create_access_token(
    subject: str,
    secret: str,
    expires_minutes: int = DEFAULT_ACCESS_TOKEN_MINUTES,
    algorithm: str = DEFAULT_ALGORITHM,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
        **(extra_claims or {}),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(token: str, secret: str, algorithm: str = DEFAULT_ALGORITHM) -> dict[str, Any]:
    try:
        return jwt.decode(token, secret, algorithms=[algorithm])
    except JWTError as exc:
        raise TokenError(str(exc)) from exc
