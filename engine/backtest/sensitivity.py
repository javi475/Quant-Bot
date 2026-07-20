"""Parameter sensitivity analysis (DOC 3 §9, DOC 7 §3.5): perturbs one
parameter across evenly-spaced offsets within +/-20% of its base value and
checks how much Sharpe degrades at the worst point. Flags instability at a
degradation > 30% (DOC 1 §2.3 sensitivity gate).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Callable

from engine.backtest.runner import BacktestRunner
from sdk.ate_smp.models.bar import Bar
from sdk.ate_smp.models.strategy_config import StrategyConfig
from sdk.ate_smp.strategy_base import StrategyBase

DEFAULT_PERTURBATION_PCT = 0.20
DEFAULT_NUM_POINTS = 5
DEFAULT_DEGRADATION_GATE = 0.30


@dataclass(frozen=True)
class SensitivityPoint:
    offset_pct: float
    value: float
    sharpe: float


@dataclass(frozen=True)
class SensitivityResult:
    param_name: str
    base_sharpe: float
    degradation_pct: float
    stable: bool
    points: list[SensitivityPoint] = field(default_factory=list)


def _linspace(low: float, high: float, num_points: int) -> list[float]:
    if num_points == 1:
        return [0.0]
    step = (high - low) / (num_points - 1)
    return [low + step * i for i in range(num_points)]


class ParameterSensitivityAnalyzer:
    def __init__(
        self,
        runner: BacktestRunner,
        perturbation_pct: float = DEFAULT_PERTURBATION_PCT,
        num_points: int = DEFAULT_NUM_POINTS,
        degradation_gate: float = DEFAULT_DEGRADATION_GATE,
    ) -> None:
        self.runner = runner
        self.perturbation_pct = perturbation_pct
        self.num_points = num_points
        self.degradation_gate = degradation_gate

    def run(
        self,
        strategy_factory: Callable[[], StrategyBase],
        config: StrategyConfig,
        bars: list[Bar],
        initial_capital: float,
        param_name: str,
    ) -> SensitivityResult:
        base_value = config.parameters.get(param_name)
        if base_value is None:
            raise ValueError(f"parameter '{param_name}' not present in config.parameters")

        offsets = _linspace(-self.perturbation_pct, self.perturbation_pct, self.num_points)
        points: list[SensitivityPoint] = []
        base_sharpe = None

        for offset in offsets:
            value = base_value * (1 + offset)
            perturbed_params = dict(config.parameters)
            perturbed_params[param_name] = value
            perturbed_config = dataclasses.replace(config, parameters=perturbed_params)

            strategy = strategy_factory()
            strategy.initialize(perturbed_config)
            result = self.runner.run(strategy, bars, initial_capital)
            sharpe = result.metrics["sharpe"]

            points.append(SensitivityPoint(offset_pct=offset, value=value, sharpe=sharpe))
            if offset == 0.0:
                base_sharpe = sharpe

        if base_sharpe is None:
            # 0.0 offset isn't guaranteed to land exactly on a grid point for
            # even num_points; fall back to the closest offset to zero.
            base_sharpe = min(points, key=lambda p: abs(p.offset_pct)).sharpe

        min_sharpe = min(p.sharpe for p in points)
        degradation = (base_sharpe - min_sharpe) / base_sharpe if base_sharpe > 0 else 1.0
        stable = degradation <= self.degradation_gate

        return SensitivityResult(
            param_name=param_name,
            base_sharpe=base_sharpe,
            degradation_pct=degradation,
            stable=stable,
            points=points,
        )
