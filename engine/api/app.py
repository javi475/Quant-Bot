"""Engine internal API (DOC 2 §6, :9000). Internal-only per the DOC 2 open
questions' conservative default — bind to localhost/private ranges only, and
put it behind Nginx access control at deployment time (DOC 6 §4.8). This is
the interface the Dashboard Backend (and Hermes) use to control the Engine;
it never talks to strategy code or venues directly.
"""

from __future__ import annotations

import asyncio
import dataclasses

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from engine.api.schemas import LoadStrategyRequest, SwapStrategyRequest
from engine.core.engine import AlgorithmEngine
from engine.risk.risk_config import RiskConfig, RiskConfigError
from engine.strategy.serialization import decode_config


def create_app(engine: AlgorithmEngine, ws_broadcast_interval_seconds: float = 1.0) -> FastAPI:
    app = FastAPI(title="ATE-SMP Engine API")
    app.state.engine = engine

    def _require_strategy(strategy_id: str) -> None:
        if strategy_id not in engine.strategies:
            raise HTTPException(status_code=404, detail=f"unknown strategy_id '{strategy_id}'")

    @app.post("/engine/strategies/load")
    async def load_strategy(req: LoadStrategyRequest):
        try:
            config = decode_config(req.config)
            await engine.load_strategy(req.strategy_id, config, req.module_path, req.class_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "loaded", "strategy_id": req.strategy_id}

    @app.post("/engine/strategies/{strategy_id}/swap")
    async def swap_strategy(strategy_id: str, req: SwapStrategyRequest):
        _require_strategy(strategy_id)
        await engine.swap_strategy(strategy_id, req.module_path, req.class_name)
        return {"status": "swapped", "strategy_id": strategy_id}

    @app.post("/engine/strategies/{strategy_id}/enable")
    async def enable_strategy(strategy_id: str):
        _require_strategy(strategy_id)
        await engine.enable_strategy(strategy_id)
        return {"status": "enabled", "strategy_id": strategy_id}

    @app.post("/engine/strategies/{strategy_id}/disable")
    async def disable_strategy(strategy_id: str):
        _require_strategy(strategy_id)
        await engine.disable_strategy(strategy_id)
        return {"status": "disabled", "strategy_id": strategy_id}

    @app.get("/engine/state")
    async def get_state():
        return await engine.get_state_snapshot()

    @app.get("/engine/risk/params")
    async def get_risk_params():
        return dataclasses.asdict(engine.risk_manager.config)

    @app.put("/engine/risk/params")
    async def update_risk_params(updates: dict):
        current = engine.risk_manager.config
        merged = {**dataclasses.asdict(current), **updates}
        try:
            candidate = RiskConfig.from_dict(merged)
        except RiskConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        # Mutate in place: every collaborator constructed with this same
        # RiskConfig instance (PositionSizer, BreakerManager, SafeModeManager)
        # reads its fields fresh on every call, so this takes effect on the
        # very next Engine cycle without any restart or re-wiring.
        for f in dataclasses.fields(RiskConfig):
            setattr(current, f.name, getattr(candidate, f.name))
        return dataclasses.asdict(current)

    @app.post("/engine/halt")
    async def halt():
        await engine.halt()
        return {"status": "halted"}

    @app.post("/engine/flatten")
    async def flatten():
        await engine.flatten()
        return {"status": "flattened"}

    @app.post("/engine/kill")
    async def kill():
        await engine.kill()
        return {"status": "killed"}

    @app.websocket("/engine/ws")
    async def engine_ws(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                snapshot = await engine.get_state_snapshot()
                await websocket.send_json({"type": "risk_update", **snapshot})
                await asyncio.sleep(ws_broadcast_interval_seconds)
        except WebSocketDisconnect:
            pass

    return app
