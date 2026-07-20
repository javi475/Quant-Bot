from datetime import datetime, timedelta, timezone

import pytest

from engine.backtest.regime import (
    classify_trend,
    classify_volatility,
    compute_atr,
    regime_breakdown,
    true_range,
)

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_true_range_basic():
    assert true_range(high=110, low=95, prev_close=100) == 15  # high-low is the widest


def test_classify_trend_insufficient_history_defaults_sideways():
    closes = [100.0] * 10
    assert classify_trend(closes, index=5, sma_period=200) == "sideways"


def test_classify_trend_bull_when_price_above_band():
    closes = [100.0] * 199 + [110.0]  # price well above the flat 200-SMA
    assert classify_trend(closes, index=199, sma_period=200, band_pct=0.02) == "bull"


def test_classify_trend_bear_when_price_below_band():
    closes = [100.0] * 199 + [90.0]
    assert classify_trend(closes, index=199, sma_period=200, band_pct=0.02) == "bear"


def test_classify_trend_sideways_within_band():
    closes = [100.0] * 199 + [100.5]
    assert classify_trend(closes, index=199, sma_period=200, band_pct=0.02) == "sideways"


def test_compute_atr_zero_before_enough_history():
    highs = [101.0] * 5
    lows = [99.0] * 5
    closes = [100.0] * 5
    assert compute_atr(highs, lows, closes, index=2, period=14) == 0.0


def test_compute_atr_positive_with_enough_history():
    n = 20
    highs = [101.0 + i * 0.1 for i in range(n)]
    lows = [99.0 + i * 0.1 for i in range(n)]
    closes = [100.0 + i * 0.1 for i in range(n)]
    atr = compute_atr(highs, lows, closes, index=n - 1, period=14)
    assert atr > 0


def test_classify_volatility_defaults_medium_before_enough_history():
    highs = [101.0] * 5
    lows = [99.0] * 5
    closes = [100.0] * 5
    assert classify_volatility(highs, lows, closes, index=2) == "medium"


def test_classify_volatility_high_for_recent_spike():
    n = 120
    highs = [100.5] * n
    lows = [99.5] * n
    closes = [100.0] * n
    # inject a volatility spike right at the end
    highs[-1] = 120.0
    lows[-1] = 80.0
    label = classify_volatility(highs, lows, closes, index=n - 1, atr_period=14, lookback=90)
    assert label == "high"


def test_regime_breakdown_requires_matching_lengths():
    bars = []
    equity_curve = [(T0, 100.0)]
    with pytest.raises(ValueError):
        regime_breakdown(bars, equity_curve)


def test_regime_breakdown_structure():
    from sdk.ate_smp.models.bar import Bar
    from common.enums import Timeframe

    n = 30
    bars = [
        Bar(
            asset="BTC/USD",
            timeframe=Timeframe.D1,
            timestamp=T0 + timedelta(days=i),
            open=100 + i * 0.1,
            high=100 + i * 0.1 + 0.5,
            low=100 + i * 0.1 - 0.5,
            close=100 + i * 0.1,
            volume=10.0,
        )
        for i in range(n)
    ]
    equity_curve = [(b.timestamp, 10_000 + i * 10) for i, b in enumerate(bars)]

    breakdown = regime_breakdown(bars, equity_curve)
    assert "by_trend" in breakdown and "by_volatility" in breakdown
    for section in breakdown.values():
        for stats in section.values():
            assert {"sharpe", "mean_return", "count"} <= stats.keys()
