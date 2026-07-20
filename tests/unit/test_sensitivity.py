import pytest

from ate_smp import AssetClass, StrategyConfig, Timeframe
from ate_smp.strategy_base import StrategyBase
from engine.backtest.sensitivity import ParameterSensitivityAnalyzer, _linspace


class DummyStrategy(StrategyBase):
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


class _FakeResult:
    def __init__(self, sharpe: float) -> None:
        self.metrics = {"sharpe": sharpe}


class _FakeRunner:
    """Stands in for BacktestRunner so the sharpe-vs-parameter relationship can
    be controlled precisely, independent of strategy/backtest mechanics."""

    def __init__(self, sharpe_fn, param_name: str = "threshold") -> None:
        self.sharpe_fn = sharpe_fn
        self.param_name = param_name

    def run(self, strategy, bars, initial_capital):
        value = strategy.config.parameters[self.param_name]
        return _FakeResult(self.sharpe_fn(value))


def make_config(threshold: float = 10.0) -> StrategyConfig:
    return StrategyConfig(
        asset_class=AssetClass.CRYPTO,
        symbols=("BTC/USD",),
        timeframes=(Timeframe.D1,),
        parameters={"threshold": threshold},
    )


def test_linspace_endpoints_and_count():
    values = _linspace(-0.2, 0.2, 5)
    assert len(values) == 5
    assert values[0] == pytest.approx(-0.2)
    assert values[-1] == pytest.approx(0.2)
    assert values[2] == pytest.approx(0.0)


def test_linspace_single_point():
    assert _linspace(-0.2, 0.2, 1) == [0.0]


def test_perturbation_offsets_match_expected_values():
    runner = _FakeRunner(sharpe_fn=lambda v: 1.0)
    analyzer = ParameterSensitivityAnalyzer(runner, perturbation_pct=0.20, num_points=5)
    result = analyzer.run(DummyStrategy, make_config(10.0), bars=[], initial_capital=1.0, param_name="threshold")

    values = sorted(p.value for p in result.points)
    assert values == pytest.approx([8.0, 9.0, 10.0, 11.0, 12.0])


def test_symmetric_degradation_flags_instability():
    # sharpe peaks at the base value and falls off symmetrically -> degradation
    # of (2.0 - 1.0) / 2.0 = 0.5, above the default 0.30 gate.
    runner = _FakeRunner(sharpe_fn=lambda v: 2.0 - abs(v - 10.0) * 0.5)
    analyzer = ParameterSensitivityAnalyzer(runner, perturbation_pct=0.20, num_points=5, degradation_gate=0.30)
    result = analyzer.run(DummyStrategy, make_config(10.0), bars=[], initial_capital=1.0, param_name="threshold")

    assert result.base_sharpe == pytest.approx(2.0)
    assert result.degradation_pct == pytest.approx(0.5)
    assert not result.stable


def test_flat_sharpe_is_stable():
    runner = _FakeRunner(sharpe_fn=lambda v: 1.5)
    analyzer = ParameterSensitivityAnalyzer(runner, perturbation_pct=0.20, num_points=5)
    result = analyzer.run(DummyStrategy, make_config(10.0), bars=[], initial_capital=1.0, param_name="threshold")
    assert result.degradation_pct == pytest.approx(0.0)
    assert result.stable


def test_missing_parameter_raises():
    runner = _FakeRunner(sharpe_fn=lambda v: 1.0)
    analyzer = ParameterSensitivityAnalyzer(runner)
    with pytest.raises(ValueError):
        analyzer.run(DummyStrategy, make_config(10.0), bars=[], initial_capital=1.0, param_name="nonexistent")
