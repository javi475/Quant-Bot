import fakeredis
import httpx
import pytest

from common.enums import AssetClass, Timeframe
from engine.api.app import create_app
from engine.backtest.cost_model import TransactionCostModel
from engine.connectors.paper import PaperConnector
from engine.connectors.price_feed import ReplayPriceFeed
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
from engine.core.engine import AlgorithmEngine
from engine.strategy.serialization import encode_config
from sdk.ate_smp.models.strategy_config import StrategyConfig


def make_engine():
    feed = ReplayPriceFeed()
    connector = PaperConnector("paper1", AssetClass.CRYPTO, feed, TransactionCostModel(), initial_capital=100_000.0)
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
    return engine, connector


async def make_client(engine):
    app = create_app(engine)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://engine-test")


def webhook_config_payload() -> dict:
    config = StrategyConfig(
        asset_class=AssetClass.CRYPTO, symbols=("BTC/USD",), timeframes=(Timeframe.D1,), connector_id="paper1"
    )
    return encode_config(config)


@pytest.mark.asyncio
async def test_load_strategy_via_api():
    engine, _ = make_engine()
    async with await make_client(engine) as client:
        resp = await client.post(
            "/engine/strategies/load",
            json={"strategy_id": "strat_1", "config": webhook_config_payload()},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "loaded"
        assert "strat_1" in engine.strategies


@pytest.mark.asyncio
async def test_load_strategy_unknown_connector_returns_400():
    engine, _ = make_engine()
    config = StrategyConfig(
        asset_class=AssetClass.CRYPTO, symbols=("BTC/USD",), timeframes=(Timeframe.D1,), connector_id="nope"
    )
    async with await make_client(engine) as client:
        resp = await client.post(
            "/engine/strategies/load", json={"strategy_id": "strat_1", "config": encode_config(config)}
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_enable_disable_unknown_strategy_returns_404():
    engine, _ = make_engine()
    async with await make_client(engine) as client:
        resp = await client.post("/engine/strategies/nonexistent/enable")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_enable_disable_roundtrip():
    engine, _ = make_engine()
    async with await make_client(engine) as client:
        await client.post(
            "/engine/strategies/load", json={"strategy_id": "strat_1", "config": webhook_config_payload()}
        )
        resp = await client.post("/engine/strategies/strat_1/disable")
        assert resp.status_code == 200
        assert not engine.strategies["strat_1"].enabled

        resp = await client.post("/engine/strategies/strat_1/enable")
        assert resp.status_code == 200
        assert engine.strategies["strat_1"].enabled


@pytest.mark.asyncio
async def test_get_state_returns_snapshot():
    engine, _ = make_engine()
    async with await make_client(engine) as client:
        resp = await client.get("/engine/state")
        assert resp.status_code == 200
        body = resp.json()
        assert "equity" in body
        assert "safe_mode" in body


@pytest.mark.asyncio
async def test_halt_flatten_kill_endpoints():
    engine, connector = make_engine()
    async with await make_client(engine) as client:
        resp = await client.post("/engine/halt")
        assert resp.json()["status"] == "halted"

        resp = await client.post("/engine/flatten")
        assert resp.json()["status"] == "flattened"

        resp = await client.post("/engine/kill")
        assert resp.json()["status"] == "killed"

    events = engine.repository.all_risk_events()
    types = {e.event_type.value for e in events}
    assert {"manual_halt", "kill_switch"} <= types
