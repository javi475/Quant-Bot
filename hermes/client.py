"""HMAC-signed HTTP client Hermes uses to talk to the Dashboard Backend
(DOC 5 §9) — its only channel into the system. Hermes never touches the
Engine, a venue, or strategy source directly; every command here goes
through the same `/api/hermes/command` surface a human operator's Telegram
bot would use, so the backend has one narrow, auditable entry point for
agent-driven actions rather than two.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

import httpx

from backend.app.auth.hmac_auth import compute_hermes_signature

HERMES_COMMAND_PATH = "/api/hermes/command"


class HermesClientError(Exception):
    """Carries the backend's actual HTTP status code, same reasoning as
    backend.app.engine_client.EngineClientError: callers need to tell a
    rejected command (4xx) apart from an unreachable/broken backend (5xx)."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HermesClient:
    def __init__(self, http_client: httpx.AsyncClient, hmac_secret: str) -> None:
        self.http = http_client
        self.secret = hmac_secret

    async def _command(self, command: str, **extra: Any) -> Any:
        payload = {"command": command, **extra}
        body = json.dumps(payload).encode("utf-8")
        timestamp = str(time.time())
        signature = compute_hermes_signature(self.secret, timestamp, "POST", HERMES_COMMAND_PATH, body)

        try:
            response = await self.http.post(
                HERMES_COMMAND_PATH,
                content=body,
                headers={
                    "X-Hermes-Signature": signature,
                    "X-Hermes-Timestamp": timestamp,
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise HermesClientError(f"command '{command}' failed: connection error: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except ValueError:
                pass
            raise HermesClientError(f"command '{command}' failed: {detail}", response.status_code)

        return response.json()["result"]

    async def status(self) -> dict:
        return await self._command("status")

    async def positions(self) -> dict:
        return await self._command("positions")

    async def risk_get(self) -> dict:
        return await self._command("risk_get")

    async def risk_set(self, updates: dict[str, Any]) -> dict:
        return await self._command("risk_set", updates=updates)

    async def trades(self, strategy_id: Optional[str] = None) -> dict:
        kwargs = {"strategy_id": strategy_id} if strategy_id else {}
        return await self._command("trades", **kwargs)

    async def halt(self) -> dict:
        return await self._command("halt")

    async def flatten(self) -> dict:
        return await self._command("flatten")

    async def kill(self) -> dict:
        return await self._command("kill")
