"""HTTP bridge from the Dashboard Backend to the Engine internal API
(DOC 2 §6, :9000). Takes an `httpx.AsyncClient` rather than a bare base URL
so tests can point it at an in-process ASGI Engine app via
`httpx.ASGITransport` — exactly like the M4 end-to-end smoke test does —
without a real network or a second process.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from engine.strategy.serialization import encode_config
from sdk.ate_smp.models.strategy_config import StrategyConfig


class EngineClientError(Exception):
    pass


class EngineClient:
    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self.http = http_client

    async def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        response = await self.http.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise EngineClientError(f"{method} {path} -> {response.status_code}: {response.text}")
        return response.json()

    async def load_strategy(
        self,
        strategy_id: str,
        config: StrategyConfig,
        module_path: Optional[str] = None,
        class_name: Optional[str] = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/engine/strategies/load",
            json={
                "strategy_id": strategy_id,
                "config": encode_config(config),
                "module_path": module_path,
                "class_name": class_name,
            },
        )

    async def swap_strategy(self, strategy_id: str, module_path: str, class_name: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/engine/strategies/{strategy_id}/swap",
            json={"module_path": module_path, "class_name": class_name},
        )

    async def enable_strategy(self, strategy_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/engine/strategies/{strategy_id}/enable")

    async def disable_strategy(self, strategy_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/engine/strategies/{strategy_id}/disable")

    async def get_state(self) -> dict[str, Any]:
        return await self._request("GET", "/engine/state")

    async def get_risk_params(self) -> dict[str, Any]:
        return await self._request("GET", "/engine/risk/params")

    async def update_risk_params(self, updates: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", "/engine/risk/params", json=updates)

    async def halt(self) -> dict[str, Any]:
        return await self._request("POST", "/engine/halt")

    async def flatten(self) -> dict[str, Any]:
        return await self._request("POST", "/engine/flatten")

    async def kill(self) -> dict[str, Any]:
        return await self._request("POST", "/engine/kill")
