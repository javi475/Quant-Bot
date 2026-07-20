from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from ate_smp import AssetClass, Direction, Signal, StrategyBase, StrategyConfig, Timeframe
from ate_smp.models.bar import Bar
from engine.backtest.cost_model import TransactionCostModel
from engine.backtest.runner import BacktestRunner, LookAheadBiasError

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
ZERO_COST = TransactionCostModel()  # no fees, no slippage


class ScriptedStrategy(StrategyBase):
    """Emits a pre-scripted signal after processing the bar at a given index."""

    def __init__(self, script: dict[int, Signal]) -> None:
        super().__init__()
        self._script = script
        self._bar_index = -1

    def initialize(self, config: StrategyConfig) -> None:
        self.config = config

    def on_bar(self, bar):
        self._bar_index += 1
        signal = self._script.get(self._bar_index)
        return [signal] if signal else []

    def on_tick(self, tick):
        return []

    def on_fill(self, fill):
        pass

    def get_parameters_schema(self):
        return []

    def get_win_probability(self) -> float:
        return 0.5

    def get_win_loss_ratio(self) -> float:
        return 1.0

    def get_state(self) -> dict[str, Any]:
        return {"bar_index": self._bar_index}

    def set_state(self, state: dict[str, Any]) -> None:
        self._bar_index = state.get("bar_index", -1)


def make_bar(asset, day, open_, high, low, close, volume=100.0):
    return Bar(
        asset=asset,
        timeframe=Timeframe.D1,
        timestamp=T0 + timedelta(days=day),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def flat_bar(asset, day, price, volume=100.0):
    return make_bar(asset, day, price, price + 0.5, price - 0.5, price, volume)


def make_config(**parameters) -> StrategyConfig:
    return StrategyConfig(
        asset_class=AssetClass.CRYPTO,
        symbols=("BTC/USD",),
        timeframes=(Timeframe.D1,),
        parameters=parameters,
    )


def test_signal_fills_at_next_bar_open_not_current_close():
    # bar[0] closes at 100 but bar[1] gaps up to open=105 — if the fill used
    # bar[0]'s close instead of bar[1]'s open, this test would catch it.
    bars = [
        make_bar("BTC/USD", 0, open_=99, high=100.5, low=98.5, close=100),
        make_bar("BTC/USD", 1, open_=105, high=106, low=104, close=106),
        make_bar("BTC/USD", 2, open_=107, high=108, low=106, close=107),
    ]
    script = {0: Signal(timestamp=T0, asset="BTC/USD", direction=Direction.LONG, strength=1.0)}
    strategy = ScriptedStrategy(script)
    strategy.initialize(make_config())

    runner = BacktestRunner(ZERO_COST, position_fraction=1.0)
    result = runner.run(strategy, bars, initial_capital=10_000)

    assert len(result.trades) == 0  # never exited, so no closed trade yet
    # equity at bar[1] should reflect a fill at 105, not 100
    expected_quantity = 10_000 / 105
    _, equity_at_bar1 = result.equity_curve[1]
    assert equity_at_bar1 == pytest.approx(expected_quantity * 106)


def test_chronological_order_enforced():
    bars = [
        flat_bar("BTC/USD", 1, 100),
        flat_bar("BTC/USD", 0, 99),  # out of order
    ]
    strategy = ScriptedStrategy({})
    strategy.initialize(make_config())
    runner = BacktestRunner(ZERO_COST)
    with pytest.raises(LookAheadBiasError):
        runner.run(strategy, bars, initial_capital=10_000)


def test_long_round_trip_pnl_with_zero_costs():
    bars = [flat_bar("BTC/USD", i, price) for i, price in enumerate([100, 101, 102, 103, 104])]
    script = {
        0: Signal(timestamp=T0, asset="BTC/USD", direction=Direction.LONG, strength=1.0),
        2: Signal(timestamp=T0, asset="BTC/USD", direction=Direction.EXIT_LONG, strength=1.0),
    }
    strategy = ScriptedStrategy(script)
    strategy.initialize(make_config())

    runner = BacktestRunner(ZERO_COST, position_fraction=1.0)
    result = runner.run(strategy, bars, initial_capital=100_000)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.side == "long"
    assert trade.entry_price == pytest.approx(101)  # bar[1].open, one bar after the signal
    assert trade.exit_price == pytest.approx(103)  # bar[3].open
    expected_quantity = 100_000 / 101
    assert trade.quantity == pytest.approx(expected_quantity)
    assert trade.pnl == pytest.approx(expected_quantity * (103 - 101))


def test_short_round_trip_pnl_with_zero_costs():
    bars = [flat_bar("BTC/USD", i, price) for i, price in enumerate([100, 99, 98, 95, 94])]
    script = {
        0: Signal(timestamp=T0, asset="BTC/USD", direction=Direction.SHORT, strength=1.0),
        2: Signal(timestamp=T0, asset="BTC/USD", direction=Direction.EXIT_SHORT, strength=1.0),
    }
    strategy = ScriptedStrategy(script)
    strategy.initialize(make_config())

    runner = BacktestRunner(ZERO_COST, position_fraction=1.0)
    result = runner.run(strategy, bars, initial_capital=100_000)

    trade = result.trades[0]
    assert trade.side == "short"
    assert trade.entry_price == pytest.approx(99)
    assert trade.exit_price == pytest.approx(95)
    expected_quantity = 100_000 / 99
    assert trade.pnl == pytest.approx(expected_quantity * (99 - 95))  # short profits as price falls


def test_fees_and_slippage_reduce_pnl():
    bars = [flat_bar("BTC/USD", i, price) for i, price in enumerate([100, 101, 102, 103])]
    script = {
        0: Signal(timestamp=T0, asset="BTC/USD", direction=Direction.LONG, strength=1.0),
        1: Signal(timestamp=T0, asset="BTC/USD", direction=Direction.EXIT_LONG, strength=1.0),
    }

    zero_cost_strategy = ScriptedStrategy(dict(script))
    zero_cost_strategy.initialize(make_config())
    zero_cost_result = BacktestRunner(ZERO_COST).run(zero_cost_strategy, bars, 100_000)

    costly_model = TransactionCostModel(taker_fee=0.01, slippage_bps=50.0)
    costly_strategy = ScriptedStrategy(dict(script))
    costly_strategy.initialize(make_config())
    costly_result = BacktestRunner(costly_model).run(costly_strategy, bars, 100_000)

    assert costly_result.trades[0].pnl < zero_cost_result.trades[0].pnl


def test_no_pyramiding_ignores_duplicate_entry():
    bars = [flat_bar("BTC/USD", i, price) for i, price in enumerate([100, 101, 102, 103])]
    script = {
        0: Signal(timestamp=T0, asset="BTC/USD", direction=Direction.LONG, strength=1.0),
        1: Signal(timestamp=T0, asset="BTC/USD", direction=Direction.LONG, strength=1.0),  # ignored
    }
    strategy = ScriptedStrategy(script)
    strategy.initialize(make_config())
    result = BacktestRunner(ZERO_COST).run(strategy, bars, 100_000)

    # Only one position ever opened; cash fully committed once, second signal is a no-op.
    assert result.equity_curve[2][1] == pytest.approx(result.equity_curve[1][1] * 102 / 101)


def test_exit_signal_mismatched_side_is_ignored():
    bars = [flat_bar("BTC/USD", i, price) for i, price in enumerate([100, 101, 102])]
    script = {
        0: Signal(timestamp=T0, asset="BTC/USD", direction=Direction.LONG, strength=1.0),
        1: Signal(timestamp=T0, asset="BTC/USD", direction=Direction.EXIT_SHORT, strength=1.0),
    }
    strategy = ScriptedStrategy(script)
    strategy.initialize(make_config())
    result = BacktestRunner(ZERO_COST).run(strategy, bars, 100_000)
    assert len(result.trades) == 0  # EXIT_SHORT doesn't close a long position


def test_multi_asset_positions_tracked_independently():
    bars = [
        flat_bar("BTC/USD", 0, 100),
        flat_bar("ETH/USD", 0, 10),
        flat_bar("BTC/USD", 1, 110),
        flat_bar("ETH/USD", 1, 11),
    ]
    script = {
        0: Signal(timestamp=T0, asset="BTC/USD", direction=Direction.LONG, strength=0.5),
    }
    strategy = ScriptedStrategy(script)
    strategy.initialize(
        StrategyConfig(
            asset_class=AssetClass.CRYPTO,
            symbols=("BTC/USD", "ETH/USD"),
            timeframes=(Timeframe.D1,),
        )
    )
    result = BacktestRunner(ZERO_COST, position_fraction=1.0).run(strategy, bars, 100_000)
    # BTC position opens at bar index 2 (next BTC bar after the bar-0 signal); ETH bars
    # untouched. No exceptions, and equity accounts for both assets' last known prices.
    assert result.equity_curve[-1][1] > 0


def test_reproducibility_same_inputs_same_outputs():
    bars = [flat_bar("BTC/USD", i, price) for i, price in enumerate([100, 101, 99, 103, 105, 102])]
    script = {
        0: Signal(timestamp=T0, asset="BTC/USD", direction=Direction.LONG, strength=1.0),
        3: Signal(timestamp=T0, asset="BTC/USD", direction=Direction.EXIT_LONG, strength=1.0),
    }

    def run_once():
        strategy = ScriptedStrategy(dict(script))
        strategy.initialize(make_config())
        return BacktestRunner(TransactionCostModel(taker_fee=0.001, slippage_bps=5)).run(
            strategy, bars, 50_000
        )

    result_a = run_once()
    result_b = run_once()

    assert result_a.equity_curve == result_b.equity_curve
    assert result_a.metrics == result_b.metrics
    assert [t.pnl for t in result_a.trades] == [t.pnl for t in result_b.trades]


def test_rejects_nonpositive_initial_capital():
    strategy = ScriptedStrategy({})
    strategy.initialize(make_config())
    with pytest.raises(ValueError):
        BacktestRunner(ZERO_COST).run(strategy, [flat_bar("BTC/USD", 0, 100)], initial_capital=0)


def test_empty_bars_returns_initial_capital_as_final_equity():
    strategy = ScriptedStrategy({})
    strategy.initialize(make_config())
    result = BacktestRunner(ZERO_COST).run(strategy, [], initial_capital=10_000)
    assert result.final_equity == 10_000
    assert result.equity_curve == []
