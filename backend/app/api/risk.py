"""DOC 2 §6 /api/risk: GET/PUT risk parameters (DOC 4 §8 — human-controlled
only; Hermes may propose strategy-parameter changes, never these) and the
breaker/risk-event history.

The backend and Engine are separate processes (:8000 and :9000) — GET/PUT
here proxy straight through EngineClient to the Engine's own
/engine/risk/params endpoint, which is what actually mutates the RiskConfig
instance shared by the running RiskManager/BreakerManager/PositionSizer.
There is no separate backend-side copy of risk parameters to keep in sync."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.auth.dependencies import get_current_subject
from backend.app.engine_client import EngineClientError

router = APIRouter(prefix="/api/risk", tags=["risk"], dependencies=[Depends(get_current_subject)])


@router.get("/params")
async def get_params(request: Request) -> dict:
    try:
        return await request.app.state.engine_client.get_risk_params()
    except EngineClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.put("/params")
async def update_params(updates: dict, request: Request) -> dict:
    try:
        return await request.app.state.engine_client.update_risk_params(updates)
    except EngineClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/breaker-history")
async def breaker_history(request: Request) -> list[dict]:
    events = await request.app.state.trade_repository.list_risk_events()
    return [
        {
            "event_type": e.event_type.value,
            "severity": e.severity.value,
            "description": e.description,
            "action_taken": e.action_taken,
            "safe_mode_activated": e.safe_mode_activated,
            "occurred_at": e.occurred_at.isoformat(),
        }
        for e in events
    ]
