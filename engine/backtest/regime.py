"""Regime classification and regime-stratified performance (DOC 3 §1
RegimeFilter, DOC 7 §3.7). Two independent dimensions are classified per
bar — trend (bull/bear/sideways) via a banded 200-period SMA, and volatility
(low/medium/high) via an ATR percentile rank over a rolling window — matching
the `allowed_trend` / `allowed_volatility` fields strategies already declare
on `RegimeFilter`.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime

from engine.backtest.metrics import sharpe_ratio
from sdk.ate_smp.models.bar import Bar

DEFAULT_SMA_PERIOD = 200
DEFAULT_TREND_BAND_PCT = 0.02
DEFAULT_ATR_PERIOD = 14
DEFAULT_VOL_LOOKBACK = 90
DEFAULT_LOW_PERCENTILE = 33.0
DEFAULT_HIGH_PERCENTILE = 67.0


def classify_trend(
    closes: list[float],
    index: int,
    sma_period: int = DEFAULT_SMA_PERIOD,
    band_pct: float = DEFAULT_TREND_BAND_PCT,
) -> str:
    if index < sma_period - 1:
        return "sideways"
    window = closes[index - sma_period + 1 : index + 1]
    sma = statistics.mean(window)
    price = closes[index]
    if sma <= 0:
        return "sideways"
    if price > sma * (1 + band_pct):
        return "bull"
    if price < sma * (1 - band_pct):
        return "bear"
    return "sideways"


def true_range(high: float, low: float, prev_close: float) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def compute_atr(
    highs: list[float], lows: list[float], closes: list[float], index: int, period: int = DEFAULT_ATR_PERIOD
) -> float:
    if index < period:
        return 0.0
    trs = [
        true_range(highs[i], lows[i], closes[i - 1])
        for i in range(index - period + 1, index + 1)
    ]
    return statistics.mean(trs)


def classify_volatility(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    index: int,
    atr_period: int = DEFAULT_ATR_PERIOD,
    lookback: int = DEFAULT_VOL_LOOKBACK,
    low_percentile: float = DEFAULT_LOW_PERCENTILE,
    high_percentile: float = DEFAULT_HIGH_PERCENTILE,
) -> str:
    if index < atr_period:
        return "medium"

    window_start = max(atr_period, index - lookback + 1)
    atr_series = [compute_atr(highs, lows, closes, i, atr_period) for i in range(window_start, index + 1)]
    if len(atr_series) < 2:
        return "medium"

    current_atr = atr_series[-1]
    sorted_atr = sorted(atr_series)
    rank_pct = sum(1 for a in sorted_atr if a <= current_atr) / len(sorted_atr) * 100

    if rank_pct <= low_percentile:
        return "low"
    if rank_pct >= high_percentile:
        return "high"
    return "medium"


def regime_breakdown(bars: list[Bar], equity_curve: list[tuple[datetime, float]]) -> dict:
    """Tags each bar-over-bar equity return with the trend/volatility regime
    active at that bar, then reports per-regime Sharpe/mean-return/count."""
    if len(bars) != len(equity_curve):
        raise ValueError("bars and equity_curve must be the same length (one point per bar)")

    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]

    by_trend: dict[str, list[float]] = defaultdict(list)
    by_volatility: dict[str, list[float]] = defaultdict(list)

    for i in range(1, len(bars)):
        prev_equity = equity_curve[i - 1][1]
        if prev_equity == 0:
            continue
        ret = (equity_curve[i][1] - prev_equity) / prev_equity

        by_trend[classify_trend(closes, i)].append(ret)
        by_volatility[classify_volatility(highs, lows, closes, i)].append(ret)

    def summarize(returns_by_label: dict[str, list[float]]) -> dict:
        return {
            label: {
                "sharpe": sharpe_ratio(returns),
                "mean_return": statistics.mean(returns) if returns else 0.0,
                "count": len(returns),
            }
            for label, returns in returns_by_label.items()
        }

    return {"by_trend": summarize(by_trend), "by_volatility": summarize(by_volatility)}
