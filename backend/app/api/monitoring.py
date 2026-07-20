"""DOC 2 §6 /api/monitoring: thin proxies over the Engine's own
get_state_snapshot() (M4), plus a polling WebSocket. WS auth resolves DOC 2's
open question in favor of a query-param token (?token=...) checked once at
connect time, since a WebSocket handshake has no header-based Authorization
round-trip the way REST does."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect

from backend.app.auth.dependencies import get_current_subject
from backend.app.auth.security import TokenError, decode_access_token

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

DEFAULT_WS_BROADCAST_INTERVAL_SECONDS = 1.0


@router.get("/state", dependencies=[Depends(get_current_subject)])
async def get_state(request: Request) -> dict:
    return await request.app.state.engine_client.get_state()


@router.get("/positions", dependencies=[Depends(get_current_subject)])
async def positions(request: Request) -> dict:
    state = await request.app.state.engine_client.get_state()
    return {
        "open_position_count": state.get("open_position_count"),
        "gross_exposure_value": state.get("gross_exposure_value"),
    }


@router.get("/risk-status", dependencies=[Depends(get_current_subject)])
async def risk_status(request: Request) -> dict:
    state = await request.app.state.engine_client.get_state()
    return {"safe_mode": state.get("safe_mode"), "halted": state.get("halted")}


@router.get("/system-health", dependencies=[Depends(get_current_subject)])
async def system_health(request: Request) -> dict:
    state = await request.app.state.engine_client.get_state()
    return {"equity": state.get("equity"), "strategies": state.get("strategies")}


@router.websocket("/ws")
async def monitoring_ws(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    try:
        if not token:
            raise TokenError("missing token")
        decode_access_token(token, websocket.app.state.jwt_secret)
    except TokenError:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    try:
        while True:
            state = await websocket.app.state.engine_client.get_state()
            await websocket.send_json({"type": "risk_update", **state})
            await asyncio.sleep(DEFAULT_WS_BROADCAST_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        pass
