from datetime import datetime, timedelta, timezone

import pytest

from ate_smp import AssetClass, StrategyConfig, Timeframe
from ate_smp.models.bar import Bar
from ate_smp.strategy_base import StrategyBase
from engine.backtest.cost_model import TransactionCostModel
from engine.backtest.runner import BacktestRunner
from engine.backtest.walk_forward import WalkForwardAnalyzer

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


class NoopStrategy(StrategyBase):
    def initialize(self, config):
        self.config = config

    def on_bar(self, bar):
        return []

    def on_tick(self, tick):
        return []

    def on_fill(self, fill):
        pass

    def get_parameters_schema(self):
        return []

    def get_win_probability(self):
        return 0.5

    def get_win_loss_ratio(self):
        return 1.0

    def get_state(self):
        return {}

    def set_state(self, state):
        pass


def make_bars(n: int) -> list[Bar]:
    return [
        Bar(
            asset="BTC/USD",
            timeframe=Timeframe.D1,
            timestamp=T0 + timedelta(days=i),
            open=100 + i,
            high=100 + i + 1,
            low=100 + i - 1,
            close=100 + i,
            volume=10.0,
        )
        for i in range(n)
    ]


def make_config():
    return StrategyConfig(asset_class=AssetClass.CRYPTO, symbols=("BTC/USD",), timeframes=(Timeframe.D1,))


def make_analyzer(**overrides):
    runner = BacktestRunner(TransactionCostModel())
    return WalkForwardAnalyzer(runner, **overrides)


def test_produces_all_windows_with_enough_data():
    analyzer = make_analyzer(num_windows=5)
    result = analyzer.run(NoopStrategy, make_config(), make_bars(500), initial_capital=10_000)
    assert len(result.windows) == 5
    assert result.oos_sharpe == 0.0  # flat equity everywhere -> zero variance -> zero sharpe
    assert not result.passed  # 0.0 < 1.5 gate


def test_raises_when_too_few_bars_for_any_window():
    analyzer = make_analyzer(num_windows=5)
    with pytest.raises(ValueError):
        analyzer.run(NoopStrategy, make_config(), make_bars(3), initial_capital=10_000)


def test_raises_when_num_windows_exceeds_bar_count():
    analyzer = make_analyzer(num_windows=10)
    with pytest.raises(ValueError):
        analyzer.run(NoopStrategy, make_config(), make_bars(5), initial_capital=10_000)


def test_invalid_split_ratio_rejected():
    runner = BacktestRunner(TransactionCostModel())
    with pytest.raises(ValueError):
        WalkForwardAnalyzer(runner, is_oos_split=1.5)
    with pytest.raises(ValueError):
        WalkForwardAnalyzer(runner, is_oos_split=0.0)


def test_passed_true_when_gates_configured_loosely():
    analyzer = make_analyzer(num_windows=5, oos_sharpe_gate=-1.0, degradation_gate=2.0)
    result = analyzer.run(NoopStrategy, make_config(), make_bars(500), initial_capital=10_000)
    assert result.passed
