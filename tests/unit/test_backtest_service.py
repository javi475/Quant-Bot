from datetime import datetime, timedelta, timezone

import pytest

from backend.app.services.backtest_service import BacktestService, BacktestServiceError
from common.enums import AssetClass, Timeframe
from sdk.ate_smp.models.bar import Bar
from sdk.ate_smp.models.strategy_config import StrategyConfig

T0 = datetime(2021, 1, 1, tzinfo=timezone.utc)

SCRIPTED_SOURCE = """
from ate_smp import StrategyBase, Direction, Signal

class ScriptedStrategy(StrategyBase):
    def initialize(self, config):
        self.config = config
        self._bar_index = -1

    def on_bar(self, bar):
        self._bar_index += 1
        if self._bar_index % 10 == 0:
            return [Signal(timestamp=bar.timestamp, asset=bar.asset, direction=Direction.LONG, strength=1.0)]
        if self._bar_index % 10 == 5:
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
        return 1.8

    def get_state(self):
        return {"bar_index": self._bar_index}

    def set_state(self, state):
        self._bar_index = state.get("bar_index", -1)
"""

MALICIOUS_SOURCE = "import os\nfrom ate_smp import StrategyBase\nclass Bad(StrategyBase):\n    pass\n"


def make_bars(n: int, seed_prices=None) -> list[Bar]:
    import random

    rng = random.Random(7)
    price = 100.0
    bars = []
    for i in range(n):
        price = max(1.0, price * (1 + rng.gauss(0, 0.01)))
        bars.append(
            Bar(
                asset="BTC/USD", timeframe=Timeframe.D1, timestamp=T0 + timedelta(days=i),
                open=price, high=price * 1.01, low=price * 0.99, close=price, volume=100.0,
            )
        )
    return bars


def make_config() -> StrategyConfig:
    return StrategyConfig(asset_class=AssetClass.CRYPTO, symbols=("BTC/USD",), timeframes=(Timeframe.D1,))


def test_run_backtest_returns_metrics_and_gate_summaries():
    service = BacktestService()
    bars = make_bars(200)
    summary = service.run_backtest(SCRIPTED_SOURCE, "ScriptedStrategy", make_config(), bars, 30_000.0)

    assert "sharpe" in summary.metrics
    assert summary.walk_forward is not None
    assert summary.monte_carlo is not None
    assert isinstance(summary.gates_passed, bool)


def test_run_backtest_rejects_malicious_source():
    service = BacktestService()
    bars = make_bars(200)
    with pytest.raises(Exception):  # StrategySandboxViolation propagates from the loader
        service.run_backtest(MALICIOUS_SOURCE, "Bad", make_config(), bars, 30_000.0)


def test_run_backtest_requires_bars():
    service = BacktestService()
    with pytest.raises(BacktestServiceError):
        service.run_backtest(SCRIPTED_SOURCE, "ScriptedStrategy", make_config(), [], 30_000.0)


def test_walk_forward_skipped_with_too_few_bars():
    service = BacktestService()
    bars = make_bars(10)
    summary = service.run_backtest(SCRIPTED_SOURCE, "ScriptedStrategy", make_config(), bars, 30_000.0)
    assert summary.walk_forward is None
    assert not summary.gates_passed
    assert any("walk-forward" in f for f in summary.gate_failures)


def test_monte_carlo_skipped_without_trades():
    service = BacktestService()
    # A strategy that never trades produces no closed trades to simulate.
    noop_source = SCRIPTED_SOURCE.replace(
        "if self._bar_index % 10 == 0:", "if False:"
    ).replace("if self._bar_index % 10 == 5:", "if False:")
    bars = make_bars(200)
    summary = service.run_backtest(
        noop_source, "ScriptedStrategy", make_config(), bars, 30_000.0, run_walk_forward=False
    )
    assert summary.monte_carlo is None
    assert not summary.gates_passed


def test_get_result_and_list_results():
    service = BacktestService()
    bars = make_bars(200)
    summary = service.run_backtest(
        SCRIPTED_SOURCE, "ScriptedStrategy", make_config(), bars, 30_000.0,
        run_walk_forward=False, run_monte_carlo=False,
    )
    fetched = service.get_result(summary.run_id)
    assert fetched.run_id == summary.run_id
    assert service.list_results() == [summary]


def test_get_unknown_result_raises():
    service = BacktestService()
    with pytest.raises(BacktestServiceError):
        service.get_result("nonexistent")
