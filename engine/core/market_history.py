"""Rolling per-asset market history the Engine feeds from every bar it sees,
used for correlation checks (DOC 4 §6) and regime classification (DOC 3 §1).
Kept separate from the Engine class itself since it's pure bookkeeping.
"""

from __future__ import annotations

from collections import defaultdict, deque

from sdk.ate_smp.models.bar import Bar

DEFAULT_LOOKBACK = 200  # covers both the 30-day correlation window and the 200-period SMA


class MarketHistoryTracker:
    def __init__(self, lookback: int = DEFAULT_LOOKBACK) -> None:
        self.lookback = lookback
        self._last_close: dict[str, float] = {}
        self._returns: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=lookback))
        self._closes: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=lookback))
        self._highs: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=lookback))
        self._lows: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=lookback))

    def on_bar(self, bar: Bar) -> None:
        prev = self._last_close.get(bar.asset)
        if prev is not None and prev != 0:
            self._returns[bar.asset].append((bar.close - prev) / prev)
        self._last_close[bar.asset] = bar.close
        self._closes[bar.asset].append(bar.close)
        self._highs[bar.asset].append(bar.high)
        self._lows[bar.asset].append(bar.low)

    def get_returns(self, asset: str, lookback_days: int | None = None) -> list[float]:
        returns = list(self._returns.get(asset, []))
        return returns[-lookback_days:] if lookback_days else returns

    def get_closes(self, asset: str) -> list[float]:
        return list(self._closes.get(asset, []))

    def get_highs(self, asset: str) -> list[float]:
        return list(self._highs.get(asset, []))

    def get_lows(self, asset: str) -> list[float]:
        return list(self._lows.get(asset, []))
