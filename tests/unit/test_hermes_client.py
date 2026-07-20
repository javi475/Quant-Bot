"""HermesClient tested against a real backend app (ASGITransport, no real
network) — same pattern as test_engine_client.py for EngineClient."""

import fakeredis
import httpx
import pytest

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
from hermes.client import HermesClient, HermesClientError

HERMES_SECRET = "hermes-client-test-secret"


async def make_backend():
    feed = ReplayPriceFeed()
    connector = PaperConnector("paper1", AssetClass.CRYPTO, feed, TransactionCostModel(), initial_capital=100_000.0)
    await connector.connect({})
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
    engine_transport = httpx.ASGITransport(app=create_engine_app(engine))
    engine_http = httpx.AsyncClient(transport=engine_transport, base_url="http://engine-test")
    engine_client = EngineClient(engine_http)

    backend_app = create_app(
        jwt_secret="jwt-secret",
        dashboard_username="admin",
        dashboard_password_hash=hash_password("pw"),
        totp_secret="JBSWY3DPEHPK3PXP",
        hermes_hmac_secret=HERMES_SECRET,
        strategy_registry=InMemoryStrategyRegistry(),
        backtest_service=BacktestService(),
        connector_registry=ConnectorRegistry(derive_fernet_key("jwt-secret")),
        engine_client=engine_client,
        trade_repository=repo,
    )
    return backend_app, engine, engine_http


@pytest.fixture
async def hermes_client():
    backend_app, engine, engine_http = await make_backend()
    transport = httpx.ASGITransport(app=backend_app)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://backend-test")
    client = HermesClient(http_client, HERMES_SECRET)
    yield client, engine
    await http_client.aclose()
    await engine_http.aclose()


@pytest.mark.asyncio
async def test_status(hermes_client):
    client, _ = hermes_client
    status = await client.status()
    assert status["equity"] == 100_000.0


@pytest.mark.asyncio
async def test_positions(hermes_client):
    client, _ = hermes_client
    positions = await client.positions()
    assert positions["open_position_count"] == 0


@pytest.mark.asyncio
async def test_risk_get_and_set(hermes_client):
    client, engine = hermes_client
    params = await client.risk_get()
    assert params["max_drawdown"] == 0.15

    updated = await client.risk_set({"max_drawdown": 0.20})
    assert updated["max_drawdown"] == 0.20
    assert engine.risk_manager.config.max_drawdown == 0.20


@pytest.mark.asyncio
async def test_risk_set_invalid_value_raises_client_error(hermes_client):
    client, _ = hermes_client
    with pytest.raises(HermesClientError) as exc_info:
        await client.risk_set({"max_drawdown": 99.0})
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_trades_empty(hermes_client):
    client, _ = hermes_client
    result = await client.trades()
    assert result["trades"] == []


@pytest.mark.asyncio
async def test_halt_flatten_kill(hermes_client):
    client, _ = hermes_client
    assert (await client.halt())["status"] == "halted"
    assert (await client.flatten())["status"] == "flattened"
    assert (await client.kill())["status"] == "killed"


@pytest.mark.asyncio
async def test_wrong_secret_rejected():
    backend_app, engine, engine_http = await make_backend()
    transport = httpx.ASGITransport(app=backend_app)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://backend-test")
    client = HermesClient(http_client, "wrong-secret")

    with pytest.raises(HermesClientError) as exc_info:
        await client.status()
    assert exc_info.value.status_code == 401

    await http_client.aclose()
    await engine_http.aclose()
