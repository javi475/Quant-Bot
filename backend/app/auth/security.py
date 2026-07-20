"""Password hashing, JWT issuance/verification, and TOTP 2FA (DOC 2 §6,
US-030). Deliberately minimal for the dashboard backend's first milestone —
a single operator account (DASHBOARD_USERNAME/PASSWORD + TOTP_SECRET, per
DOC 5 §2) rather than a full multi-user system, matching "solo quant
developer" as the primary user (DOC 1 §1.4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pyotp
from jose import JWTError, jwt
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEFAULT_ALGORITHM = "HS256"
DEFAULT_ACCESS_TOKEN_MINUTES = 30  # DOC 1 US-030: 30-minute session


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def verify_totp(totp_secret: str, code: str) -> bool:
    return pyotp.TOTP(totp_secret).verify(code, valid_window=1)


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
