"""Production entry point for the Dashboard Backend (DOC 2 §6, :8000).

Bootstraps all dependencies — Engine, connectors, risk, registries, and the
FastAPI app — and starts the uvicorn server. All secrets and credentials are
defined here; move them to environment variables before real-money use.

Usage:
    python -m backend.run
    python -m backend.run --reload          (development with auto-reload)
    python -m backend.run --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import argparse

import httpx
import uvicorn

from fastapi import FastAPI

from backend.app.app import create_app
from backend.app.auth.security import hash_password
from backend.app.engine_client import EngineClient
from backend.app.services.backtest_service import BacktestService
from backend.app.services.connector_registry import ConnectorRegistry, derive_fernet_key
from backend.app.services.strategy_registry import InMemoryStrategyRegistry
from common.enums import AssetClass
from engine.api.app import create_app as create_engine_app
from engine.backtest.cost_model import TransactionCostModel
from engine.connectors.paper import PaperConnector
from engine.connectors.price_feed import ReplayPriceFeed
from engine.core.engine import AlgorithmEngine
from engine.core.execution_manager import ExecutionManager
from engine.core.heartbeat import HeartbeatWriter
from engine.core.repository import InMemoryTradeRepository
from engine.core.signal_scheduler import SignalScheduler
from engine.core.state_manager import StateManager
from engine.risk.breaker import BreakerManager
from engine.risk.correlation import CorrelationManager
from engine.risk.position_sizer import PositionSizer
from engine.risk.risk_config import RiskConfig
from engine.risk.risk_manager import RiskManager
from engine.risk.safe_mode import SafeModeManager

# ---------------------------------------------------------------------------
# Credentials — change these to your own.
# ---------------------------------------------------------------------------
DASHBOARD_USERNAME: str = "adminmarcos"
DASHBOARD_PASSWORD: str = "Hotdog789$"

JWT_SECRET: str = "ate-smp-dashboard-jwt-secret-change-in-production"
HERMES_HMAC_SECRET: str = "ate-smp-hermes-hmac-secret-change-in-production"


def build_app() -> FastAPI:
    """Build the full dashboard backend app with all dependencies wired up."""
    import fakeredis

    # -- Engine ---------------------------------------------------------------
    feed = ReplayPriceFeed()
    connector = PaperConnector(
        "paper1", AssetClass.CRYPTO, feed, TransactionCostModel(), initial_capital=100_000.0
    )
    repo = InMemoryTradeRepository()
    redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    config = RiskConfig()
    risk_manager = RiskManager(config, PositionSizer(config), SafeModeManager(config))
    engine = AlgorithmEngine(
        connectors={"paper1": connector},
        risk_manager=risk_manager,
        breaker_manager=BreakerManager(config),
        correlation_manager=CorrelationManager(config),
        execution_manager=ExecutionManager({"paper1": connector}, repo),
        state_manager=StateManager(redis_client, repo),
        scheduler=SignalScheduler(),
        heartbeat=HeartbeatWriter(redis_client, interval_seconds=5, ttl_seconds=15),
        repository=repo,
        redis_client=redis_client,
    )

    engine_app = create_engine_app(engine)
    engine_transport = httpx.ASGITransport(app=engine_app)
    engine_http = httpx.AsyncClient(transport=engine_transport, base_url="http://engine-test")
    engine_client = EngineClient(engine_http)
    # -------------------------------------------------------------------------

    fernet_key = derive_fernet_key(JWT_SECRET)
    dashboard_password_hash = hash_password(DASHBOARD_PASSWORD)

    app = create_app(
        jwt_secret=JWT_SECRET,
        dashboard_username=DASHBOARD_USERNAME,
        dashboard_password_hash=dashboard_password_hash,
        hermes_hmac_secret=HERMES_HMAC_SECRET,
        strategy_registry=InMemoryStrategyRegistry(),
        backtest_service=BacktestService(),
        connector_registry=ConnectorRegistry(fernet_key),
        engine_client=engine_client,
        trade_repository=repo,
    )
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ATE-SMP Dashboard Backend")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    uvicorn.run(
        "backend.run:build_app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        factory=True,
    )
