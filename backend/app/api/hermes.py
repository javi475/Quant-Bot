"""DOC 2 §6, DOC 5 §9 /api/hermes/command: HMAC-authenticated (not JWT —
Hermes is a separate agent, not the human operator), narrow command surface
for the orchestration agent. Full parity with every dashboard endpoint isn't
the point; DOC 5's own command table only ever needs Hermes to check status
and pull the same three emergency levers a human has via /api/deployment."""

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
        elif command == "halt":
            result = await engine_client.halt()
        elif command == "flatten":
            result = await engine_client.flatten()
        elif command == "kill":
            result = await engine_client.kill()
        else:
            raise HTTPException(status_code=400, detail=f"unknown command '{command}'")
    except EngineClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"command": command, "result": result}
