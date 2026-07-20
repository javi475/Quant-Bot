"""DOC 2 §6: /api/auth/login, /verify-2fa (folded into login for this
milestone — TOTP is checked in the same request as the password rather than
as a separate round-trip), /refresh."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.app.auth.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    verify_password,
    verify_totp,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str
    totp_code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    access_token: str


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request) -> TokenResponse:
    state = request.app.state
    if req.username != state.dashboard_username or not verify_password(
        req.password, state.dashboard_password_hash
    ):
        raise HTTPException(status_code=401, detail="invalid username or password")
    if not verify_totp(state.totp_secret, req.totp_code):
        raise HTTPException(status_code=401, detail="invalid 2FA code")

    token = create_access_token(req.username, state.jwt_secret)
    return TokenResponse(access_token=token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, request: Request) -> TokenResponse:
    state = request.app.state
    try:
        payload = decode_access_token(req.access_token, state.jwt_secret)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc

    token = create_access_token(payload["sub"], state.jwt_secret)
    return TokenResponse(access_token=token)
