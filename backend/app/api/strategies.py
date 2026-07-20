"""DOC 2 §6 strategy CRUD: upload, version, activate (DOC 3 §3, US-001/002)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.app.auth.dependencies import get_current_subject
from backend.app.services.strategy_registry import StrategyRegistryError
from common.enums import AssetClass

router = APIRouter(prefix="/api/strategies", tags=["strategies"], dependencies=[Depends(get_current_subject)])


class CreateStrategyRequest(BaseModel):
    name: str
    asset_class: str
    tags: list[str] = []


class UploadVersionRequest(BaseModel):
    source_code: str
    class_name: str
    parameters: dict = {}


def _strategy_dict(record) -> dict:
    return {
        "id": record.id,
        "name": record.name,
        "asset_class": record.asset_class.value,
        "state": record.state.value,
        "tags": record.tags,
        "active_version_id": record.active_version_id,
    }


def _version_dict(version) -> dict:
    return {
        "id": version.id,
        "version": version.version,
        "class_name": version.class_name,
        "checksum_sha256": version.checksum_sha256,
        "is_active": version.is_active,
        "created_at": version.created_at.isoformat(),
    }


@router.post("")
async def create_strategy(req: CreateStrategyRequest, request: Request) -> dict:
    try:
        record = await request.app.state.strategy_registry.create_strategy(
            req.name, AssetClass(req.asset_class), req.tags
        )
    except (StrategyRegistryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _strategy_dict(record)


@router.get("")
async def list_strategies(request: Request) -> list[dict]:
    records = await request.app.state.strategy_registry.list_strategies()
    return [_strategy_dict(r) for r in records]


@router.post("/{strategy_id}/versions")
async def upload_version(strategy_id: str, req: UploadVersionRequest, request: Request) -> dict:
    try:
        version = await request.app.state.strategy_registry.upload_version(
            strategy_id, req.source_code, req.class_name, req.parameters
        )
    except StrategyRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _version_dict(version)


@router.get("/{strategy_id}/versions")
async def list_versions(strategy_id: str, request: Request) -> list[dict]:
    try:
        versions = await request.app.state.strategy_registry.list_versions(strategy_id)
    except StrategyRegistryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_version_dict(v) for v in versions]


@router.post("/{strategy_id}/versions/{version}/activate")
async def activate_version(strategy_id: str, version: str, request: Request) -> dict:
    try:
        target = await request.app.state.strategy_registry.activate_version(strategy_id, version)
    except StrategyRegistryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _version_dict(target)
