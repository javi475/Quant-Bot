import fakeredis
import httpx
import pytest

from backend.app.engine_client import EngineClient, EngineClientError
from common.enums import AssetClass, Timeframe
from engine.api.app import create_app
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
from sdk.ate_smp.models.strategy_config import StrategyConfig


def make_engine():
    feed = ReplayPriceFeed()
    connector = PaperConnector("paper1", AssetClass.CRYPTO, feed, TransactionCostModel(), initial_capital=100_000.0)
    repo = InMemoryTradeRepository()
    redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    config = RiskConfig()
    risk_manager = RiskManager(config, PositionSizer(config), SafeModeManager(config))
    return AlgorithmEngine(
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


@pytest.fixture
async def engine_client():
    engine = make_engine()
    await engine.connectors["paper1"].connect({})
    app = create_app(engine)
    transport = httpx.ASGITransport(app=app)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://engine-test")
    client = EngineClient(http_client)
    yield client, engine
    await http_client.aclose()
    await engine.scheduler.stop_all()
    for running in engine.strategies.values():
        if running.process is not None:
            await running.process.shutdown()


def webhook_config() -> StrategyConfig:
    return StrategyConfig(
        asset_class=AssetClass.CRYPTO, symbols=("BTC/USD",), timeframes=(Timeframe.D1,), connector_id="paper1"
    )


@pytest.mark.asyncio
async def test_load_strategy(engine_client):
    client, engine = engine_client
    result = await client.load_strategy("strat_1", webhook_config())
    assert result["status"] == "loaded"
    assert "strat_1" in engine.strategies


@pytest.mark.asyncio
async def test_load_strategy_unknown_connector_raises(engine_client):
    client, _ = engine_client
    bad_config = StrategyConfig(
        asset_class=AssetClass.CRYPTO, symbols=("BTC/USD",), timeframes=(Timeframe.D1,), connector_id="nope"
    )
    with pytest.raises(EngineClientError):
        await client.load_strategy("strat_1", bad_config)


@pytest.mark.asyncio
async def test_enable_disable_strategy(engine_client):
    client, engine = engine_client
    await client.load_strategy("strat_1", webhook_config())

    await client.disable_strategy("strat_1")
    assert not engine.strategies["strat_1"].enabled

    await client.enable_strategy("strat_1")
    assert engine.strategies["strat_1"].enabled


@pytest.mark.asyncio
async def test_enable_unknown_strategy_raises(engine_client):
    client, _ = engine_client
    with pytest.raises(EngineClientError):
        await client.enable_strategy("nonexistent")


@pytest.mark.asyncio
async def test_get_state(engine_client):
    client, _ = engine_client
    state = await client.get_state()
    assert "equity" in state
    assert "safe_mode" in state


@pytest.mark.asyncio
async def test_halt_flatten_kill(engine_client):
    client, _ = engine_client
    assert (await client.halt())["status"] == "halted"
    assert (await client.flatten())["status"] == "flattened"
    assert (await client.kill())["status"] == "killed"


@pytest.mark.asyncio
async def test_get_and_update_risk_params(engine_client):
    client, engine = engine_client
    params = await client.get_risk_params()
    assert params["kelly_multiplier"] == 0.25

    updated = await client.update_risk_params({"kelly_multiplier": 0.30})
    assert updated["kelly_multiplier"] == 0.30
    # Propagates to the actual shared RiskConfig instance the Engine's
    # RiskManager reads from, not just a disconnected copy.
    assert engine.risk_manager.config.kelly_multiplier == 0.30


@pytest.mark.asyncio
async def test_update_risk_params_rejects_invalid_value(engine_client):
    client, _ = engine_client
    with pytest.raises(EngineClientError):
        await client.update_risk_params({"kelly_multiplier": 99.0})
