import asyncio
import json
from datetime import datetime, timedelta, timezone

import fakeredis
import pytest

from common.enums import AssetClass, Direction, Timeframe
from common.redis_keys import SIGNAL_QUEUE
from engine.backtest.cost_model import TransactionCostModel
from engine.connectors.paper import PaperConnector
from engine.connectors.price_feed import ReplayPriceFeed
from engine.core.engine import AlgorithmEngine, DEFAULT_WEBHOOK_WIN_PROBABILITY, DEFAULT_WEBHOOK_WIN_LOSS_RATIO
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
from engine.strategy.serialization import encode_signal
from sdk.ate_smp.models.bar import Bar
from sdk.ate_smp.models.signal import Signal
from sdk.ate_smp.models.strategy_config import StrategyConfig

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

SCRIPTED_STRATEGY_SOURCE = """
from ate_smp import StrategyBase, Direction, Signal

class ScriptedStrategy(StrategyBase):
    def initialize(self, config):
        self.config = config
        self._bar_index = -1

    def on_bar(self, bar):
        self._bar_index += 1
        if self._bar_index == 0:
            return [Signal(timestamp=bar.timestamp, asset=bar.asset, direction=Direction.LONG, strength=1.0)]
        if self._bar_index == 2:
            return [Signal(timestamp=bar.timestamp, asset=bar.asset, direction=Direction.EXIT_LONG, strength=1.0)]
        return []

    def on_tick(self, tick):
        return []

    def on_fill(self, fill):
        pass

    def get_parameters_schema(self):
        return []

    def get_win_probability(self):
        return 0.6

    def get_win_loss_ratio(self):
        return 2.0

    def get_state(self):
        return {"bar_index": self._bar_index}

    def set_state(self, state):
        self._bar_index = state.get("bar_index", -1)
"""


def make_bar(asset: str, day: int, close: float) -> Bar:
    return Bar(
        asset=asset, timeframe=Timeframe.D1, timestamp=T0 + timedelta(days=day),
        open=close, high=close + 0.5, low=close - 0.5, close=close, volume=100.0,
    )


class Harness:
    def __init__(self):
        self.feed = ReplayPriceFeed()
        self.connector = PaperConnector(
            "paper1", AssetClass.CRYPTO, self.feed, TransactionCostModel(), initial_capital=100_000.0
        )
        self.repo = InMemoryTradeRepository()
        self.redis = fakeredis.FakeAsyncRedis(decode_responses=True)
        self.config = RiskConfig()
        self.risk_manager = RiskManager(self.config, PositionSizer(self.config), SafeModeManager(self.config))
        self.breaker_manager = BreakerManager(self.config)
        self.correlation_manager = CorrelationManager(self.config)
        self.execution_manager = ExecutionManager({"paper1": self.connector}, self.repo)
        self.state_manager = StateManager(self.redis, self.repo)
        self.scheduler = SignalScheduler()
        self.heartbeat = HeartbeatWriter(self.redis, interval_seconds=5, ttl_seconds=15)

        self.engine = AlgorithmEngine(
            connectors={"paper1": self.connector},
            risk_manager=self.risk_manager,
            breaker_manager=self.breaker_manager,
            correlation_manager=self.correlation_manager,
            execution_manager=self.execution_manager,
            state_manager=self.state_manager,
            scheduler=self.scheduler,
            heartbeat=self.heartbeat,
            repository=self.repo,
            redis_client=self.redis,
        )

    async def connect(self):
        await self.connector.connect({})

    async def teardown(self):
        await self.scheduler.stop_all()
        for running in self.engine.strategies.values():
            if running.process is not None:
                await running.process.shutdown()


async def _pump():
    for _ in range(3):
        await asyncio.sleep(0)


@pytest.fixture
async def harness():
    h = Harness()
    await h.connect()
    yield h
    await h.teardown()


def webhook_config(**overrides) -> StrategyConfig:
    defaults = dict(
        asset_class=AssetClass.CRYPTO,
        symbols=("BTC/USD",),
        timeframes=(Timeframe.D1,),
        connector_id="paper1",
    )
    defaults.update(overrides)
    return StrategyConfig(**defaults)


async def push_webhook_signal_for(
    harness: Harness, strategy_id: str, asset: str, direction: Direction, strength: float = 1.0
):
    signal = Signal(timestamp=T0, asset=asset, direction=direction, strength=strength)
    envelope = json.dumps({"strategy_id": strategy_id, "signal": encode_signal(signal)})
    await harness.redis.rpush(SIGNAL_QUEUE, envelope)


async def push_webhook_signal(harness: Harness, strategy_id: str, direction: Direction, strength: float = 1.0):
    await push_webhook_signal_for(harness, strategy_id, "BTC/USD", direction, strength)


# ----- Webhook-driven signal path -----

@pytest.mark.asyncio
async def test_webhook_driven_strategy_defaults_are_kelly_positive():
    assert (DEFAULT_WEBHOOK_WIN_PROBABILITY, DEFAULT_WEBHOOK_WIN_LOSS_RATIO) != (0.5, 1.0)
    p, b = DEFAULT_WEBHOOK_WIN_PROBABILITY, DEFAULT_WEBHOOK_WIN_LOSS_RATIO
    assert (p * (b + 1) - 1) / b > 0


@pytest.mark.asyncio
async def test_webhook_signal_opens_a_position(harness):
    await harness.engine.load_strategy("strat_tv", webhook_config())
    harness.feed.set_price("BTC/USD", 100.0)

    await push_webhook_signal(harness, "strat_tv", Direction.LONG)
    await harness.engine.run_cycle(T0)

    position = await harness.connector.get_position("BTC/USD")
    assert position is not None
    assert position.quantity > 0
    assert len(await harness.repo.get_open_trades("strat_tv")) == 1


@pytest.mark.asyncio
async def test_webhook_signal_for_disabled_strategy_is_dropped(harness):
    await harness.engine.load_strategy("strat_tv", webhook_config())
    await harness.engine.disable_strategy("strat_tv")
    harness.feed.set_price("BTC/USD", 100.0)

    await push_webhook_signal(harness, "strat_tv", Direction.LONG)
    await harness.engine.run_cycle(T0)

    assert await harness.connector.get_position("BTC/USD") is None


@pytest.mark.asyncio
async def test_webhook_signal_for_unknown_strategy_is_ignored(harness):
    harness.feed.set_price("BTC/USD", 100.0)
    await push_webhook_signal(harness, "no_such_strategy", Direction.LONG)
    await harness.engine.run_cycle(T0)  # must not raise
    assert await harness.connector.get_position("BTC/USD") is None


@pytest.mark.asyncio
async def test_webhook_exit_closes_the_real_open_position(harness):
    await harness.engine.load_strategy("strat_tv", webhook_config())
    harness.feed.set_price("BTC/USD", 100.0)
    await push_webhook_signal(harness, "strat_tv", Direction.LONG)
    await harness.engine.run_cycle(T0)
    assert await harness.connector.get_position("BTC/USD") is not None

    harness.feed.set_price("BTC/USD", 110.0)
    await push_webhook_signal(harness, "strat_tv", Direction.EXIT_LONG)
    await harness.engine.run_cycle(T0 + timedelta(seconds=1))

    assert await harness.connector.get_position("BTC/USD") is None
    trades = harness.repo.all_trades()
    assert trades[0].is_closed
    assert trades[0].pnl > 0


# ----- Subprocess-driven signal path -----

@pytest.mark.asyncio
async def test_subprocess_strategy_full_round_trip(harness, tmp_path):
    strategy_file = tmp_path / "scripted_strategy.py"
    strategy_file.write_text(SCRIPTED_STRATEGY_SOURCE)

    await harness.engine.load_strategy(
        "strat_py", webhook_config(), module_path=str(strategy_file), class_name="ScriptedStrategy"
    )

    running = harness.engine.strategies["strat_py"]
    assert running.win_probability == 0.6  # pulled from the real strategy, not the webhook default

    for day, price in enumerate([100.0, 101.0, 102.0, 103.0]):
        await harness.feed.push_bar(make_bar("BTC/USD", day, price))
        await _pump()
        await harness.engine.run_cycle(T0 + timedelta(days=day))

    trades = harness.repo.all_trades()
    assert len(trades) == 1
    assert trades[0].is_closed


@pytest.mark.asyncio
async def test_hot_swap_preserves_state(harness, tmp_path):
    strategy_file = tmp_path / "scripted_strategy.py"
    strategy_file.write_text(SCRIPTED_STRATEGY_SOURCE)
    await harness.engine.load_strategy(
        "strat_py", webhook_config(), module_path=str(strategy_file), class_name="ScriptedStrategy"
    )

    await harness.feed.push_bar(make_bar("BTC/USD", 0, 100.0))
    await _pump()
    await harness.engine.run_cycle(T0)  # bar_index becomes 0, LONG queued for next cycle's fill

    await harness.engine.swap_strategy("strat_py", str(strategy_file), "ScriptedStrategy")

    new_state = await harness.engine.strategies["strat_py"].process.get_state()
    assert new_state["bar_index"] == 0  # carried over via get_state()/set_state()


# ----- Strategy fault handling -----

@pytest.mark.asyncio
async def test_handle_strategy_fault_restart_true_keeps_strategy_enabled(harness, tmp_path):
    strategy_file = tmp_path / "scripted_strategy.py"
    strategy_file.write_text(SCRIPTED_STRATEGY_SOURCE)
    await harness.engine.load_strategy(
        "strat_py", webhook_config(), module_path=str(strategy_file), class_name="ScriptedStrategy"
    )
    old_process = harness.engine.strategies["strat_py"].process

    await harness.engine._handle_strategy_fault("strat_py", "timeout", restart=True)

    running = harness.engine.strategies["strat_py"]
    assert running.enabled
    assert running.process is not old_process
    assert running.process.is_running


@pytest.mark.asyncio
async def test_handle_strategy_fault_restart_false_disables_strategy(harness, tmp_path):
    strategy_file = tmp_path / "scripted_strategy.py"
    strategy_file.write_text(SCRIPTED_STRATEGY_SOURCE)
    await harness.engine.load_strategy(
        "strat_py", webhook_config(), module_path=str(strategy_file), class_name="ScriptedStrategy"
    )

    await harness.engine._handle_strategy_fault("strat_py", "crashed", restart=False)

    assert not harness.engine.strategies["strat_py"].enabled


# ----- Breaker / safe mode -----

@pytest.mark.asyncio
async def test_daily_loss_breaker_triggers_flatten_and_safe_mode(harness):
    # A single Kelly-sized position (capped at max_risk_per_trade = 2% of
    # equity) can never itself breach the -3% daily breaker even at price
    # zero, by construction — the risk system is self-consistent that way.
    # Three uncorrelated 2%-of-equity positions all crashing at once is a
    # realistic way to actually accumulate a portfolio-level loss past -3%.
    await harness.engine.load_strategy("strat_tv", webhook_config())
    assets = ["BTC/USD", "ETH/USD", "XRP/USD"]
    for i, asset in enumerate(assets):
        harness.feed.set_price(asset, 100.0)
        await push_webhook_signal_for(harness, "strat_tv", asset, Direction.LONG)
        await harness.engine.run_cycle(T0 + timedelta(seconds=i))
    for asset in assets:
        assert await harness.connector.get_position(asset) is not None

    for asset in assets:
        harness.feed.set_price(asset, 30.0)  # 70% crash on every position at once
    await harness.engine.run_cycle(T0 + timedelta(seconds=10))

    assert harness.risk_manager.safe_mode.is_active
    events = harness.repo.all_risk_events()
    assert any(e.event_type.value == "daily_loss_breaker" for e in events)


@pytest.mark.asyncio
async def test_max_loss_forced_exit(harness):
    # check_max_loss_exit is a defense-in-depth backstop for positions whose
    # loss has come to exceed max_risk_per_trade of *current* equity — which a
    # freshly Kelly-sized entry can approach but never breach. To exercise the
    # backstop itself (e.g. the position pre-dates a risk-parameter tightening,
    # or was opened before Kelly capped it this tightly), place an oversized
    # order directly through the connector, bypassing the risk pipeline.
    from common.enums import OrderSide, OrderType
    from engine.models.order import Order

    harness.feed.set_price("BTC/USD", 100.0)
    await harness.execution_manager.place_order(
        "paper1",
        Order(asset="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=700),
        "strat_tv",
    )
    assert await harness.connector.get_position("BTC/USD") is not None

    # With a single position, "this position's loss / equity" and "portfolio
    # daily loss / equity" are numerically the same ratio — so to isolate the
    # max-loss backstop from the daily breaker (2% vs 3% of equity), the move
    # must land strictly between the two, not blow past both at once.
    harness.feed.set_price("BTC/USD", 96.5)
    await harness.engine.run_cycle(T0 + timedelta(seconds=1))

    assert await harness.connector.get_position("BTC/USD") is None
    events = harness.repo.all_risk_events()
    assert any(e.event_type.value == "max_loss_stop" for e in events)


# ----- Halt / flatten / kill -----

@pytest.mark.asyncio
async def test_halt_records_event_and_blocks_nothing_by_itself(harness):
    await harness.engine.halt()
    events = harness.repo.all_risk_events()
    assert any(e.event_type.value == "manual_halt" for e in events)


@pytest.mark.asyncio
async def test_flatten_closes_all_positions(harness):
    await harness.engine.load_strategy("strat_tv", webhook_config())
    harness.feed.set_price("BTC/USD", 100.0)
    await push_webhook_signal(harness, "strat_tv", Direction.LONG)
    await harness.engine.run_cycle(T0)
    assert await harness.connector.get_position("BTC/USD") is not None

    await harness.engine.flatten()
    assert await harness.connector.get_position("BTC/USD") is None


@pytest.mark.asyncio
async def test_kill_disables_all_strategies_and_flattens(harness):
    await harness.engine.load_strategy("strat_tv", webhook_config())
    harness.feed.set_price("BTC/USD", 100.0)
    await push_webhook_signal(harness, "strat_tv", Direction.LONG)
    await harness.engine.run_cycle(T0)

    await harness.engine.kill()

    assert await harness.connector.get_position("BTC/USD") is None
    assert not harness.engine.strategies["strat_tv"].enabled
    events = harness.repo.all_risk_events()
    assert any(e.event_type.value == "kill_switch" for e in events)


# ----- State snapshot -----

@pytest.mark.asyncio
async def test_get_state_snapshot_structure(harness):
    await harness.engine.load_strategy("strat_tv", webhook_config())
    snapshot = await harness.engine.get_state_snapshot()
    assert "equity" in snapshot
    assert "safe_mode" in snapshot
    assert snapshot["strategies"]["strat_tv"]["webhook_driven"] is True


@pytest.mark.asyncio
async def test_heartbeat_written_after_run_cycle(harness):
    await harness.engine.run_cycle(T0)
    from common import redis_keys

    assert await harness.redis.get(redis_keys.HEARTBEAT_KEY) is not None
