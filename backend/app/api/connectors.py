"""DOC 2 §6 /api/connectors: credentials are Fernet-encrypted at rest
(backend.app.services.connector_registry) and never returned decrypted
through any of these routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.app.auth.dependencies import get_current_subject
from backend.app.services.connector_registry import ConnectorRegistryError
from common.enums import AssetClass

router = APIRouter(prefix="/api/connectors", tags=["connectors"], dependencies=[Depends(get_current_subject)])


class CreateConnectorRequest(BaseModel):
    name: str
    connector_type: str
    asset_class: str
    credentials: dict
    config: dict = {}


def _sanitize(record) -> dict:
    return {
        "id": record.id,
        "name": record.name,
        "connector_type": record.connector_type,
        "asset_class": record.asset_class.value,
        "is_active": record.is_active,
        "config": record.config,
    }


@router.post("")
async def create_connector(req: CreateConnectorRequest, request: Request) -> dict:
    try:
        record = request.app.state.connector_registry.create_connector(
            req.name, req.connector_type, AssetClass(req.asset_class), req.credentials, req.config
        )
    except (ConnectorRegistryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _sanitize(record)


@router.get("")
async def list_connectors(request: Request) -> list[dict]:
    return [_sanitize(r) for r in request.app.state.connector_registry.list_connectors()]


@router.get("/{connector_id}")
async def get_connector(connector_id: str, request: Request) -> dict:
    try:
        record = request.app.state.connector_registry.get_connector(connector_id)
    except ConnectorRegistryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _sanitize(record)


@router.post("/{connector_id}/test")
async def test_connector(connector_id: str, request: Request) -> dict:
    try:
        record = request.app.state.connector_registry.get_connector(connector_id)
    except ConnectorRegistryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if record.connector_type != "paper":
        return {
            "status": "not_implemented",
            "detail": (
                f"live connectivity testing for '{record.connector_type}' connectors "
                "lands with the M6 venue integrations"
            ),
        }

    from engine.connectors.paper import PaperConnector
    from engine.connectors.price_feed import ReplayPriceFeed

    test_connector_instance = PaperConnector(connector_id, record.asset_class, ReplayPriceFeed())
    await test_connector_instance.connect({})
    connected = test_connector_instance.is_connected()
    await test_connector_instance.disconnect()
    return {"status": "ok" if connected else "failed"}
