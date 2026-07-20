"""Dashboard Backend app factory (DOC 2 §6, :8000). All dependencies are
passed in explicitly — same dependency-injection pattern as
engine.api.app.create_app and webhook.app.create_app — so tests can wire it
up with in-memory registries and an EngineClient pointed at an in-process
ASGI Engine app, with no real network, database, or second process."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import auth, backtests, connectors, deployment, hermes, monitoring, risk, strategies, trades
from backend.app.engine_client import EngineClient
from backend.app.services.backtest_service import BacktestService
from backend.app.services.connector_registry import ConnectorRegistry
from backend.app.services.strategy_registry import StrategyRegistry
from engine.core.repository import TradeRepository

DEFAULT_STRATEGIES_DIR = "./strategies"
# The Vite dev server's default port (frontend/vite.config.ts). Production
# deployment terminates both dashboard frontend and backend behind the same
# Nginx host (DOC 6 §4.8), where this cross-origin allowance isn't needed —
# override via `cors_origins` there instead of relying on this default.
DEFAULT_CORS_ORIGINS = ["http://localhost:3000"]


def create_app(
    *,
    jwt_secret: str,
    dashboard_username: str,
    dashboard_password_hash: str,
    totp_secret: str,
    hermes_hmac_secret: str,
    strategy_registry: StrategyRegistry,
    backtest_service: BacktestService,
    connector_registry: ConnectorRegistry,
    engine_client: EngineClient,
    trade_repository: TradeRepository,
    strategies_dir: str = DEFAULT_STRATEGIES_DIR,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    app = FastAPI(title="ATE-SMP Dashboard Backend")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins if cors_origins is not None else DEFAULT_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.jwt_secret = jwt_secret
    app.state.dashboard_username = dashboard_username
    app.state.dashboard_password_hash = dashboard_password_hash
    app.state.totp_secret = totp_secret
    app.state.hermes_hmac_secret = hermes_hmac_secret
    app.state.strategy_registry = strategy_registry
    app.state.backtest_service = backtest_service
    app.state.connector_registry = connector_registry
    app.state.engine_client = engine_client
    app.state.trade_repository = trade_repository
    app.state.strategies_dir = strategies_dir

    app.include_router(auth.router)
    app.include_router(strategies.router)
    app.include_router(backtests.router)
    app.include_router(deployment.router)
    app.include_router(monitoring.router)
    app.include_router(connectors.router)
    app.include_router(risk.router)
    app.include_router(trades.router)
    app.include_router(hermes.router)

    return app
