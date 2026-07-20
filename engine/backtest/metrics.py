"""Backtest performance metrics: Sharpe ratio, max drawdown, win rate, profit
factor, total return (DOC 7 §3)."""

from __future__ import annotations

import math
import statistics
from datetime import datetime

from engine.backtest.types import Trade


def equity_returns(equity_curve: list[tuple[datetime, float]]) -> list[float]:
    values = [v for _, v in equity_curve]
    return [
        (values[i] - values[i - 1]) / values[i - 1]
        for i in range(1, len(values))
        if values[i - 1] != 0
    ]


def sharpe_ratio(returns: list[float], risk_free_rate: float = 0.0, periods_per_year: int = 252) -> float:
    if len(returns) < 2:
        return 0.0
    std = statistics.pstdev(returns)
    if std == 0:
        return 0.0
    period_rf = risk_free_rate / periods_per_year
    mean_excess = statistics.mean(returns) - period_rf
    return (mean_excess / std) * math.sqrt(periods_per_year)


def max_drawdown(equity_curve: list[tuple[datetime, float]]) -> float:
    peak = None
    worst = 0.0
    for _, equity in equity_curve:
        if peak is None or equity > peak:
            peak = equity
        if peak and peak > 0:
            dd = (peak - equity) / peak
            worst = max(worst, dd)
    return worst


def win_rate(trades: list[Trade]) -> float:
    closed = [t for t in trades if t.is_closed]
    if not closed:
        return 0.0
    wins = sum(1 for t in closed if t.pnl > 0)
    return wins / len(closed)


def profit_factor(trades: list[Trade]) -> float:
    closed = [t for t in trades if t.is_closed]
    gains = sum(t.pnl for t in closed if t.pnl > 0)
    losses = -sum(t.pnl for t in closed if t.pnl < 0)
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def total_return(equity_curve: list[tuple[datetime, float]]) -> float:
    if not equity_curve:
        return 0.0
    start = equity_curve[0][1]
    end = equity_curve[-1][1]
    return (end - start) / start if start else 0.0


def compute_metrics(
    equity_curve: list[tuple[datetime, float]],
    trades: list[Trade],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> dict:
    returns = equity_returns(equity_curve)
    return {
        "sharpe": sharpe_ratio(returns, risk_free_rate, periods_per_year),
        "max_drawdown": max_drawdown(equity_curve),
        "win_rate": win_rate(trades),
        "profit_factor": profit_factor(trades),
        "total_return": total_return(equity_curve),
        "num_trades": sum(1 for t in trades if t.is_closed),
    }
