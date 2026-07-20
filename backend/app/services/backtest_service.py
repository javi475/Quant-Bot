"""Runs a strategy through the M3 backtest engine and evaluates it against
the DOC 1 §2.3 / DOC 7 §3 approval gates: OOS Sharpe >= 1.5 (target) / 1.2
(threshold), walk-forward degradation <= 20% / 35%, Monte Carlo probability
of ruin < 5%.

Bars are supplied directly in the request for this milestone rather than
queried from a historical data store — the market_data hypertable and a
wired-up ccxt downloader exist (M3) but connecting them to this service is
deferred; note this clearly rather than fake a data-fetch path.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from engine.backtest.cost_model import TransactionCostModel
from engine.backtest.monte_carlo import MonteCarloSimulator
from engine.backtest.runner import BacktestRunner
from engine.backtest.walk_forward import WalkForwardAnalyzer
from engine.strategy.loader import load_class_from_source
from sdk.ate_smp.models.bar import Bar
from sdk.ate_smp.models.strategy_config import StrategyConfig

OOS_SHARPE_TARGET = 1.5
OOS_SHARPE_THRESHOLD = 1.2
DEGRADATION_TARGET = 0.20
DEGRADATION_THRESHOLD = 0.35
MAX_PROB_OF_RUIN = 0.05
MIN_BARS_FOR_WALK_FORWARD = 50


class BacktestServiceError(Exception):
    pass


@dataclass
class BacktestSummary:
    run_id: str
    metrics: dict
    walk_forward: Optional[dict]
    monte_carlo: Optional[dict]
    gates_passed: bool
    gate_failures: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class BacktestService:
    def __init__(self) -> None:
        self._results: dict[str, BacktestSummary] = {}

    def run_backtest(
        self,
        source_code: str,
        class_name: str,
        config: StrategyConfig,
        bars: list[Bar],
        initial_capital: float,
        cost_model: Optional[TransactionCostModel] = None,
        run_walk_forward: bool = True,
        run_monte_carlo: bool = True,
        monte_carlo_iterations: int = 1000,
    ) -> BacktestSummary:
        if not bars:
            raise BacktestServiceError("at least one bar is required")

        strategy_cls = load_class_from_source(source_code, class_name)
        cost_model = cost_model or TransactionCostModel()
        runner = BacktestRunner(cost_model)

        strategy = strategy_cls()
        strategy.initialize(config)
        result = runner.run(strategy, bars, initial_capital)

        gate_failures: list[str] = []

        walk_forward_summary = None
        if run_walk_forward:
            if len(bars) < MIN_BARS_FOR_WALK_FORWARD:
                gate_failures.append(
                    f"insufficient bars ({len(bars)}) for walk-forward analysis "
                    f"(need >= {MIN_BARS_FOR_WALK_FORWARD})"
                )
            else:
                analyzer = WalkForwardAnalyzer(
                    runner, oos_sharpe_gate=OOS_SHARPE_THRESHOLD, degradation_gate=DEGRADATION_THRESHOLD
                )
                wf_result = analyzer.run(strategy_cls, config, bars, initial_capital)
                walk_forward_summary = {
                    "is_sharpe": wf_result.is_sharpe,
                    "oos_sharpe": wf_result.oos_sharpe,
                    "degradation_pct": wf_result.degradation_pct,
                    "passed": wf_result.passed,
                    "meets_target": (
                        wf_result.oos_sharpe >= OOS_SHARPE_TARGET
                        and wf_result.degradation_pct <= DEGRADATION_TARGET
                    ),
                }
                if not wf_result.passed:
                    gate_failures.append(
                        f"walk-forward gate failed: OOS Sharpe {wf_result.oos_sharpe:.2f} "
                        f"(need >= {OOS_SHARPE_THRESHOLD}), degradation {wf_result.degradation_pct:.1%} "
                        f"(need < {DEGRADATION_THRESHOLD:.0%})"
                    )

        monte_carlo_summary = None
        if run_monte_carlo:
            if not result.trades:
                gate_failures.append("no closed trades to run Monte Carlo simulation on")
            else:
                mc_result = MonteCarloSimulator(iterations=monte_carlo_iterations).run(
                    result.trades, initial_capital
                )
                monte_carlo_summary = {
                    "iterations": mc_result.iterations,
                    "prob_of_ruin": mc_result.prob_of_ruin,
                    "max_drawdown_median": mc_result.max_drawdown_median,
                    "max_drawdown_p95": mc_result.max_drawdown_p95,
                }
                if mc_result.prob_of_ruin >= MAX_PROB_OF_RUIN:
                    gate_failures.append(
                        f"probability of ruin {mc_result.prob_of_ruin:.1%} >= {MAX_PROB_OF_RUIN:.0%} gate"
                    )

        summary = BacktestSummary(
            run_id=str(uuid.uuid4()),
            metrics=result.metrics,
            walk_forward=walk_forward_summary,
            monte_carlo=monte_carlo_summary,
            gates_passed=not gate_failures,
            gate_failures=gate_failures,
        )
        self._results[summary.run_id] = summary
        return summary

    def get_result(self, run_id: str) -> BacktestSummary:
        result = self._results.get(run_id)
        if result is None:
            raise BacktestServiceError(f"unknown run_id '{run_id}'")
        return result

    def list_results(self) -> list[BacktestSummary]:
        return list(self._results.values())
