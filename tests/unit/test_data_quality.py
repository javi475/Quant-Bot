from datetime import datetime, timedelta, timezone

import pytest

from common.enums import Timeframe
from engine.data.quality import detect_gaps, expected_interval, forward_fill_gaps
from sdk.ate_smp.models.bar import Bar

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_series(timestamps: list[datetime]) -> list[Bar]:
    return [
        Bar(
            asset="BTC/USD",
            timeframe=Timeframe.H1,
            timestamp=ts,
            open=100.0,
            high=100.5,
            low=99.5,
            close=100.0,
            volume=1.0,
        )
        for ts in timestamps
    ]


def test_expected_interval_mapping():
    assert expected_interval(Timeframe.H1) == timedelta(hours=1)
    assert expected_interval(Timeframe.D1) == timedelta(days=1)


def test_no_gaps_in_contiguous_series():
    bars = make_series([T0 + timedelta(hours=i) for i in range(10)])
    report = detect_gaps(bars, Timeframe.H1)
    assert report.gap_pct == 0.0
    assert not report.warn
    assert report.gaps == []


def test_detects_single_gap():
    timestamps = [T0, T0 + timedelta(hours=1), T0 + timedelta(hours=5)]  # 3 bars missing
    bars = make_series(timestamps)
    report = detect_gaps(bars, Timeframe.H1)
    assert len(report.gaps) == 1
    assert report.gaps[0].missing_bars == 3


def test_gap_percentage_and_warning_threshold():
    # 20 present bars with one large gap of 5 missing bars -> gap_pct = 5/25 = 20% > 5%
    timestamps = [T0 + timedelta(hours=i) for i in range(10)]
    timestamps += [timestamps[-1] + timedelta(hours=6 + i) for i in range(10)]
    bars = make_series(timestamps)
    report = detect_gaps(bars, Timeframe.H1)
    assert report.gap_pct == pytest.approx(5 / 25)
    assert report.warn


def test_small_gap_does_not_warn():
    # 100 bars with a single 1-bar gap -> gap_pct ~= 1/101, well under 5%
    timestamps = [T0 + timedelta(hours=i) for i in range(50)]
    timestamps += [timestamps[-1] + timedelta(hours=2 + i) for i in range(50)]
    bars = make_series(timestamps)
    report = detect_gaps(bars, Timeframe.H1)
    assert not report.warn


def test_forward_fill_inserts_flat_bars():
    timestamps = [T0, T0 + timedelta(hours=1), T0 + timedelta(hours=4)]
    bars = make_series(timestamps)
    bars[1] = Bar(
        asset="BTC/USD", timeframe=Timeframe.H1, timestamp=timestamps[1],
        open=100, high=106, low=99, close=105, volume=2.0,
    )
    filled = forward_fill_gaps(bars, Timeframe.H1)

    assert len(filled) == 5  # 3 original + 2 filled
    filled_timestamps = [b.timestamp for b in filled]
    assert filled_timestamps == [
        T0, T0 + timedelta(hours=1), T0 + timedelta(hours=2), T0 + timedelta(hours=3), T0 + timedelta(hours=4)
    ]
    # filled bars carry the previous close forward, flat, with zero volume
    assert filled[2].open == filled[2].close == 105
    assert filled[2].volume == 0.0
    assert filled[3].open == filled[3].close == 105


def test_forward_fill_noop_on_contiguous_series():
    bars = make_series([T0 + timedelta(hours=i) for i in range(5)])
    filled = forward_fill_gaps(bars, Timeframe.H1)
    assert filled == bars


def test_forward_fill_handles_short_series():
    bars = make_series([T0])
    assert forward_fill_gaps(bars, Timeframe.H1) == bars


def test_detect_gaps_handles_short_series():
    bars = make_series([T0])
    report = detect_gaps(bars, Timeframe.H1)
    assert report.gap_pct == 0.0
