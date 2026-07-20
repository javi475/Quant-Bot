"""Walk-forward analysis (DOC 3 §9, DOC 7 §3.3): splits the bar series into
`num_windows` contiguous windows, each split IS/OOS at `is_oos_split`, and
compares average in-sample vs. out-of-sample Sharpe to detect overfitting.

Pass gate (DOC 1 §2.3, DOC 7 §3): average OOS Sharpe >= 1.5 and
degradation < 35%.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Callable

from engine.backtest.runner import BacktestRunner
from sdk.ate_smp.models.bar import Bar
from sdk.ate_smp.models.strategy_config import StrategyConfig
from sdk.ate_smp.strategy_base import StrategyBase

DEFAULT_OOS_SHARPE_GATE = 1.5
DEFAULT_DEGRADATION_GATE = 0.35
MIN_IS_BARS = 10
MIN_OOS_BARS = 5


@dataclass(frozen=True)
class WalkForwardWindow:
    window_index: int
    is_sharpe: float
    oos_sharpe: float


@dataclass(frozen=True)
class WalkForwardResult:
    is_sharpe: float
    oos_sharpe: float
    degradation_pct: float
    passed: bool
    windows: list[WalkForwardWindow] = field(default_factory=list)


class WalkForwardAnalyzer:
    def __init__(
        self,
        runner: BacktestRunner,
        is_oos_split: float = 0.70,
        num_windows: int = 5,
        oos_sharpe_gate: float = DEFAULT_OOS_SHARPE_GATE,
        degradation_gate: float = DEFAULT_DEGRADATION_GATE,
    ) -> None:
        if not (0.0 < is_oos_split < 1.0):
            raise ValueError(f"is_oos_split {is_oos_split} must be in (0.0, 1.0)")
        self.runner = runner
        self.is_oos_split = is_oos_split
        self.num_windows = num_windows
        self.oos_sharpe_gate = oos_sharpe_gate
        self.degradation_gate = degradation_gate

    def run(
        self,
        strategy_factory: Callable[[], StrategyBase],
        config: StrategyConfig,
        bars: list[Bar],
        initial_capital: float,
    ) -> WalkForwardResult:
        window_size = len(bars) // self.num_windows
        if window_size == 0:
            raise ValueError(
                f"not enough bars ({len(bars)}) to form {self.num_windows} walk-forward windows"
            )

        windows: list[WalkForwardWindow] = []

        for w in range(self.num_windows):
            start = w * window_size
            end = len(bars) if w == self.num_windows - 1 else start + window_size
            window_bars = bars[start:end]

            split = int(len(window_bars) * self.is_oos_split)
            is_bars, oos_bars = window_bars[:split], window_bars[split:]
            if len(is_bars) < MIN_IS_BARS or len(oos_bars) < MIN_OOS_BARS:
                continue

            is_strategy = strategy_factory()
            is_strategy.initialize(config)
            is_result = self.runner.run(is_strategy, is_bars, initial_capital)

            oos_strategy = strategy_factory()
            oos_strategy.initialize(config)
            oos_result = self.runner.run(oos_strategy, oos_bars, initial_capital)

            windows.append(
                WalkForwardWindow(
                    window_index=w,
                    is_sharpe=is_result.metrics["sharpe"],
                    oos_sharpe=oos_result.metrics["sharpe"],
                )
            )

        if not windows:
            raise ValueError(
                f"no walk-forward window had enough bars (need >= {MIN_IS_BARS} IS "
                f"and >= {MIN_OOS_BARS} OOS bars per window)"
            )

        avg_is = statistics.mean(w.is_sharpe for w in windows)
        avg_oos = statistics.mean(w.oos_sharpe for w in windows)
        degradation = (avg_is - avg_oos) / avg_is if avg_is > 0 else 1.0
        passed = avg_oos >= self.oos_sharpe_gate and degradation < self.degradation_gate

        return WalkForwardResult(
            is_sharpe=avg_is,
            oos_sharpe=avg_oos,
            degradation_pct=degradation,
            passed=passed,
            windows=windows,
        )
