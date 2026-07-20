"""DOC 2 §6 /api/backtests: runs a saved strategy version through the M3
backtest engine. Bars are supplied directly in the request (see
backend.app.services.backtest_service for why)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.app.auth.dependencies import get_current_subject
from backend.app.services.backtest_service import BacktestServiceError
from backend.app.services.strategy_registry import StrategyRegistryError
from engine.backtest.cost_model import default_cost_model
from engine.strategy.serialization import decode_bar, decode_config

router = APIRouter(prefix="/api/backtests", tags=["backtests"], dependencies=[Depends(get_current_subject)])


class RunBacktestRequest(BaseModel):
    strategy_id: str
    version: Optional[str] = None
    config: dict
    bars: list[dict]
    initial_capital: float
    run_walk_forward: bool = True
    run_monte_carlo: bool = True


def _summary_dict(summary) -> dict:
    return {
        "run_id": summary.run_id,
        "metrics": summary.metrics,
        "walk_forward": summary.walk_forward,
        "monte_carlo": summary.monte_carlo,
        "gates_passed": summary.gates_passed,
        "gate_failures": summary.gate_failures,
        "created_at": summary.created_at.isoformat(),
    }


async def _resolve_version(request: Request, strategy_id: str, version: Optional[str]):
    registry = request.app.state.strategy_registry
    try:
        if version:
            versions = await registry.list_versions(strategy_id)
            record = next((v for v in versions if v.version == version), None)
            if record is None:
                raise HTTPException(
                    status_code=404, detail=f"strategy '{strategy_id}' has no version '{version}'"
                )
            return record
        record = await registry.get_active_version(strategy_id)
        if record is None:
            raise HTTPException(status_code=400, detail=f"strategy '{strategy_id}' has no active version")
        return record
    except StrategyRegistryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("")
async def run_backtest(req: RunBacktestRequest, request: Request) -> dict:
    version_record = await _resolve_version(request, req.strategy_id, req.version)

    config = decode_config(req.config)
    bars = [decode_bar(b) for b in req.bars]
    cost_model = default_cost_model(config.asset_class)

    try:
        summary = request.app.state.backtest_service.run_backtest(
            version_record.source_code,
            version_record.class_name,
            config,
            bars,
            req.initial_capital,
            cost_model=cost_model,
            run_walk_forward=req.run_walk_forward,
            run_monte_carlo=req.run_monte_carlo,
        )
    except BacktestServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _summary_dict(summary)


@router.get("/{run_id}")
async def get_backtest(run_id: str, request: Request) -> dict:
    try:
        summary = request.app.state.backtest_service.get_result(run_id)
    except BacktestServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _summary_dict(summary)


@router.get("")
async def list_backtests(request: Request) -> list[dict]:
    return [_summary_dict(s) for s in request.app.state.backtest_service.list_results()]
