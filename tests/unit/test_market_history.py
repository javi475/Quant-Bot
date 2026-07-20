from datetime import datetime, timedelta, timezone

from common.enums import Timeframe
from engine.core.market_history import MarketHistoryTracker
from sdk.ate_smp.models.bar import Bar

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_bar(asset: str, day: int, close: float) -> Bar:
    return Bar(
        asset=asset, timeframe=Timeframe.D1, timestamp=T0 + timedelta(days=day),
        open=close, high=close + 1, low=close - 1, close=close, volume=1.0,
    )


def test_first_bar_has_no_return():
    tracker = MarketHistoryTracker()
    tracker.on_bar(make_bar("BTC/USD", 0, 100.0))
    assert tracker.get_returns("BTC/USD") == []
    assert tracker.get_closes("BTC/USD") == [100.0]


def test_subsequent_bars_compute_returns():
    tracker = MarketHistoryTracker()
    tracker.on_bar(make_bar("BTC/USD", 0, 100.0))
    tracker.on_bar(make_bar("BTC/USD", 1, 110.0))
    assert tracker.get_returns("BTC/USD") == [0.10]


def test_lookback_window_truncates_returns():
    tracker = MarketHistoryTracker()
    for i in range(10):
        tracker.on_bar(make_bar("BTC/USD", i, 100.0 + i))
    all_returns = tracker.get_returns("BTC/USD")
    windowed = tracker.get_returns("BTC/USD", lookback_days=3)
    assert len(windowed) == 3
    assert windowed == all_returns[-3:]


def test_maxlen_bounds_stored_history():
    tracker = MarketHistoryTracker(lookback=5)
    for i in range(20):
        tracker.on_bar(make_bar("BTC/USD", i, 100.0 + i))
    assert len(tracker.get_closes("BTC/USD")) == 5
    assert len(tracker.get_highs("BTC/USD")) == 5
    assert len(tracker.get_lows("BTC/USD")) == 5


def test_tracks_multiple_assets_independently():
    tracker = MarketHistoryTracker()
    tracker.on_bar(make_bar("BTC/USD", 0, 100.0))
    tracker.on_bar(make_bar("ETH/USD", 0, 10.0))
    assert tracker.get_closes("BTC/USD") == [100.0]
    assert tracker.get_closes("ETH/USD") == [10.0]


def test_unknown_asset_returns_empty():
    tracker = MarketHistoryTracker()
    assert tracker.get_returns("NONEXISTENT") == []
    assert tracker.get_closes("NONEXISTENT") == []


def test_zero_prev_close_does_not_divide_by_zero():
    tracker = MarketHistoryTracker()
    tracker.on_bar(Bar(asset="X", timeframe=Timeframe.D1, timestamp=T0, open=0.01, high=0.02, low=0.0, close=0.0, volume=0.0))
    tracker.on_bar(Bar(asset="X", timeframe=Timeframe.D1, timestamp=T0 + timedelta(days=1), open=1, high=2, low=0.5, close=1.0, volume=1.0))
    # first close is 0 -> guarded, no ZeroDivisionError, and no return recorded for that transition
    assert tracker.get_returns("X") == []
