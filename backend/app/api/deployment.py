"""DOC 2 §6 /api/deployment: deploy/halt/flatten/kill-switch. A strategy's
source is stored as text in the registry, but the Engine's subprocess
runtime (M1) loads strategies from a file path — deploy materializes the
active version's source to disk once, here, right before telling the Engine
to load it (DOC 6 open question "strategy code in PG vs. disk": stored in
the registry, materialized to disk on deploy)."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.app.auth.dependencies import get_current_subject
from backend.app.engine_client import EngineClientError
from backend.app.services.strategy_registry import StrategyRegistryError
from engine.strategy.serialization import decode_config

router = APIRouter(prefix="/api/deployment", tags=["deployment"], dependencies=[Depends(get_current_subject)])


class DeployRequest(BaseModel):
    strategy_id: str
    config: dict
    version: Optional[str] = None


def _materialize_strategy_file(strategies_dir: str, strategy_id: str, version) -> str:
    os.makedirs(strategies_dir, exist_ok=True)
    path = os.path.join(strategies_dir, f"{strategy_id}_{version.version}.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(version.source_code)
    return path


@router.post("/deploy")
async def deploy(req: DeployRequest, request: Request) -> dict:
    registry = request.app.state.strategy_registry
    try:
        if req.version:
            versions = await registry.list_versions(req.strategy_id)
            version_record = next((v for v in versions if v.version == req.version), None)
            if version_record is None:
                raise HTTPException(
                    status_code=404, detail=f"strategy '{req.strategy_id}' has no version '{req.version}'"
                )
        else:
            version_record = await registry.get_active_version(req.strategy_id)
            if version_record is None:
                raise HTTPException(
                    status_code=400, detail=f"strategy '{req.strategy_id}' has no active version"
                )
    except StrategyRegistryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    config = decode_config(req.config)
    module_path = _materialize_strategy_file(request.app.state.strategies_dir, req.strategy_id, version_record)

    engine_client = request.app.state.engine_client
    try:
        state = await engine_client.get_state()
        already_running = req.strategy_id in state.get("strategies", {})

        if already_running:
            # DOC 3 §3: activating/redeploying a version hot-swaps a strategy
            # that's already running (state carries over via get_state()/
            # set_state()) instead of doing a fresh load.
            await engine_client.swap_strategy(req.strategy_id, module_path, version_record.class_name)
            action = "hot_swapped"
        else:
            await engine_client.load_strategy(
                req.strategy_id, config, module_path=module_path, class_name=version_record.class_name
            )
            await engine_client.enable_strategy(req.strategy_id)
            action = "deployed"
    except EngineClientError as exc:
        raise HTTPException(status_code=502, detail=f"engine rejected deployment: {exc}") from exc

    return {
        "status": action,
        "strategy_id": req.strategy_id,
        "version": version_record.version,
        "module_path": module_path,
    }


@router.post("/halt")
async def halt(request: Request) -> dict:
    try:
        return await request.app.state.engine_client.halt()
    except EngineClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/flatten")
async def flatten(request: Request) -> dict:
    try:
        return await request.app.state.engine_client.flatten()
    except EngineClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/kill-switch")
async def kill_switch(request: Request) -> dict:
    try:
        return await request.app.state.engine_client.kill()
    except EngineClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
