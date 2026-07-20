"""Monte Carlo simulation over a completed backtest's trade sequence (DOC 3
§9, DOC 7 §3.4): resample trade order (or bootstrap trade P&L with
replacement), replay each resampled sequence as its own equity path, and
report 5/50/95 percentile equity curves, drawdown percentiles, and the
probability of ruin.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from engine.backtest.types import Trade

DEFAULT_ITERATIONS = 1000
DEFAULT_RUIN_THRESHOLD = 0.5  # a 50% loss from initial capital counts as "ruin"


@dataclass(frozen=True)
class MonteCarloResult:
    iterations: int
    percentile_curves: dict[str, list[float]]  # "p5" / "p50" / "p95" -> equity path
    prob_of_ruin: float
    max_drawdown_median: float
    max_drawdown_p95: float


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    frac = rank - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * frac


class MonteCarloSimulator:
    def __init__(
        self,
        iterations: int = DEFAULT_ITERATIONS,
        resampling: str = "trade_order",
        ruin_threshold: float = DEFAULT_RUIN_THRESHOLD,
        random_seed: Optional[int] = None,
    ) -> None:
        if resampling not in ("trade_order", "returns"):
            raise ValueError(f"unknown resampling method: {resampling}")
        self.iterations = iterations
        self.resampling = resampling
        self.ruin_threshold = ruin_threshold
        self.random_seed = random_seed

    def run(self, trades: list[Trade], initial_capital: float) -> MonteCarloResult:
        closed = [t for t in trades if t.is_closed]
        if not closed:
            raise ValueError("no closed trades to simulate")
        if initial_capital <= 0:
            raise ValueError(f"initial_capital {initial_capital} must be positive")

        rng = random.Random(self.random_seed)
        pnls = [t.pnl for t in closed]
        n = len(pnls)
        ruin_floor = initial_capital * (1 - self.ruin_threshold)

        curves: list[list[float]] = []
        max_drawdowns: list[float] = []
        ruin_count = 0

        for _ in range(self.iterations):
            if self.resampling == "trade_order":
                sample = pnls[:]
                rng.shuffle(sample)
            else:
                sample = [rng.choice(pnls) for _ in range(n)]

            equity = initial_capital
            curve = [equity]
            peak = equity
            max_dd = 0.0
            ruined = False

            for pnl in sample:
                equity += pnl
                curve.append(equity)
                peak = max(peak, equity)
                if peak > 0:
                    max_dd = max(max_dd, (peak - equity) / peak)
                if equity <= ruin_floor:
                    ruined = True

            curves.append(curve)
            max_drawdowns.append(max_dd)
            if ruined:
                ruin_count += 1

        path_length = n + 1
        percentile_curves = {"p5": [], "p50": [], "p95": []}
        for i in range(path_length):
            values_at_i = sorted(curve[i] for curve in curves)
            percentile_curves["p5"].append(_percentile(values_at_i, 5))
            percentile_curves["p50"].append(_percentile(values_at_i, 50))
            percentile_curves["p95"].append(_percentile(values_at_i, 95))

        sorted_dds = sorted(max_drawdowns)

        return MonteCarloResult(
            iterations=self.iterations,
            percentile_curves=percentile_curves,
            prob_of_ruin=ruin_count / self.iterations,
            max_drawdown_median=_percentile(sorted_dds, 50),
            max_drawdown_p95=_percentile(sorted_dds, 95),
        )
