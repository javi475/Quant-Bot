"""DOC 2 §6, DOC 5 §9 /api/hermes/command: HMAC-authenticated (not JWT —
Hermes is a separate agent, not the human operator), narrow command surface
for the orchestration agent: status/positions/risk read+write and the three
emergency levers a human has via /api/deployment. Still not full parity with
every dashboard endpoint — proposal workflow, phase-gate tracking, backups,
and log access aren't built yet (see hermes/jobs.py for what's genuinely
implemented vs. honestly stubbed)."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request

from backend.app.auth.hmac_auth import verify_hermes_request
from backend.app.engine_client import EngineClientError

router = APIRouter(prefix="/api/hermes", tags=["hermes"])

HERMES_COMMAND_PATH = "/api/hermes/command"
SIGNATURE_HEADER = "X-Hermes-Signature"
TIMESTAMP_HEADER = "X-Hermes-Timestamp"


@router.post("/command")
async def hermes_command(request: Request) -> dict:
    body = await request.body()
    signature = request.headers.get(SIGNATURE_HEADER, "")
    timestamp = request.headers.get(TIMESTAMP_HEADER, "")
    secret = request.app.state.hermes_hmac_secret

    if not verify_hermes_request(secret, timestamp, "POST", HERMES_COMMAND_PATH, body, signature):
        raise HTTPException(status_code=401, detail="invalid or missing HMAC signature")

    try:
        payload = json.loads(body)
        command = payload["command"]
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"malformed command payload: {exc}") from exc

    engine_client = request.app.state.engine_client
    try:
        if command == "status":
            result = await engine_client.get_state()
        elif command == "positions":
            state = await engine_client.get_state()
            result = {
                "open_position_count": state.get("open_position_count"),
                "gross_exposure_value": state.get("gross_exposure_value"),
                "equity": state.get("equity"),
            }
        elif command == "risk_get":
            result = await engine_client.get_risk_params()
        elif command == "risk_set":
            updates = payload.get("updates")
            if not isinstance(updates, dict):
                raise HTTPException(status_code=400, detail="risk_set requires an 'updates' object")
            result = await engine_client.update_risk_params(updates)
        elif command == "trades":
            strategy_id = payload.get("strategy_id")
            trades = await request.app.state.trade_repository.list_trades(strategy_id)
            result = {
                "trades": [
                    {
                        "trade_id": t.trade_id,
                        "asset": t.asset,
                        "side": t.side,
                        "quantity": t.quantity,
                        "pnl": t.pnl,
                        "is_closed": t.is_closed,
                    }
                    for t in trades
                ]
            }
        elif command == "halt":
            result = await engine_client.halt()
        elif command == "flatten":
            result = await engine_client.flatten()
        elif command == "kill":
            result = await engine_client.kill()
        else:
            raise HTTPException(status_code=400, detail=f"unknown command '{command}'")
    except EngineClientError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc

    return {"command": command, "result": result}
