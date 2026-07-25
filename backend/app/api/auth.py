"""DOC 2 §6: /api/auth/login, /refresh."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.app.auth.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


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
