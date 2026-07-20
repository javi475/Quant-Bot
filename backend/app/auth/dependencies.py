"""FastAPI dependency requiring a valid JWT bearer token on every protected
route (DOC 2 §6). The secret is attached to `app.state.jwt_secret` by the app
factory rather than imported from an env var here, so tests can spin up an
app with an arbitrary secret."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.auth.security import TokenError, decode_access_token

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_subject(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        payload = decode_access_token(credentials.credentials, request.app.state.jwt_secret)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc
    return payload["sub"]
