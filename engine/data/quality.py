"""Historical data gap detection and forward-fill (DOC 1 §3.7, US-046: forward
fill gaps, warn if > 5%). Pure functions over an already-fetched bar series —
no network I/O, so fully deterministic and unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from common.enums import Timeframe
from sdk.ate_smp.models.bar import Bar

GAP_WARNING_THRESHOLD = 0.05

_TIMEFRAME_INTERVALS: dict[Timeframe, timedelta] = {
    Timeframe.M1: timedelta(minutes=1),
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.M30: timedelta(minutes=30),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
    Timeframe.D1: timedelta(days=1),
    Timeframe.W1: timedelta(days=7),
}


def expected_interval(timeframe: Timeframe) -> timedelta:
    return _TIMEFRAME_INTERVALS[timeframe]


@dataclass(frozen=True)
class Gap:
    start: object  # datetime of the bar before the gap
    end: object  # datetime of the bar after the gap
    missing_bars: int


@dataclass(frozen=True)
class GapReport:
    gap_pct: float
    gaps: list[Gap] = field(default_factory=list)
    warn: bool = False


def detect_gaps(bars: list[Bar], timeframe: Timeframe) -> GapReport:
    if len(bars) < 2:
        return GapReport(gap_pct=0.0, gaps=[], warn=False)

    interval = expected_interval(timeframe)
    gaps: list[Gap] = []
    missing_total = 0

    for i in range(1, len(bars)):
        delta = bars[i].timestamp - bars[i - 1].timestamp
        steps = round(delta / interval)
        missing = steps - 1
        if missing > 0:
            gaps.append(Gap(start=bars[i - 1].timestamp, end=bars[i].timestamp, missing_bars=missing))
            missing_total += missing

    total_expected = len(bars) + missing_total
    gap_pct = missing_total / total_expected if total_expected else 0.0

    return GapReport(gap_pct=gap_pct, gaps=gaps, warn=gap_pct > GAP_WARNING_THRESHOLD)


def forward_fill_gaps(bars: list[Bar], timeframe: Timeframe) -> list[Bar]:
    """Fills missing bars by carrying the previous bar's close forward as a
    flat (zero-range, zero-volume) bar at each missing timestamp."""
    if len(bars) < 2:
        return list(bars)

    interval = expected_interval(timeframe)
    filled: list[Bar] = [bars[0]]

    for i in range(1, len(bars)):
        prev = filled[-1]
        current = bars[i]
        t = prev.timestamp + interval
        while t < current.timestamp:
            filled.append(
                Bar(
                    asset=prev.asset,
                    timeframe=timeframe,
                    timestamp=t,
                    open=prev.close,
                    high=prev.close,
                    low=prev.close,
                    close=prev.close,
                    volume=0.0,
                )
            )
            t += interval
        filled.append(current)

    return filled
