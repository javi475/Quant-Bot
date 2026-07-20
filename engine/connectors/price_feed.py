"""In-memory price/bar feed backing PaperConnector. Fed either by test code
(`set_price`/`push_bar`) or, in later milestones, by an adapter that replays
historical data or forwards a real live feed — the Engine and PaperConnector
don't need to know which.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import AsyncIterator, Optional

from sdk.ate_smp.models.bar import Bar

DEFAULT_HISTORY_LIMIT = 500


class ReplayPriceFeed:
    def __init__(self, history_limit: int = DEFAULT_HISTORY_LIMIT) -> None:
        self._prices: dict[str, float] = {}
        self._queues: dict[str, asyncio.Queue[Bar]] = {}
        self._history: dict[str, list[Bar]] = defaultdict(list)
        self._history_limit = history_limit

    def set_price(self, symbol: str, price: float) -> None:
        """Directly sets a symbol's current price without emitting a bar
        (useful for quote-only tests/demos)."""
        self._prices[symbol] = price

    def get_price(self, symbol: str) -> Optional[float]:
        return self._prices.get(symbol)

    def get_history(self, symbol: str) -> list[Bar]:
        return list(self._history[symbol])

    def known_symbols(self) -> list[str]:
        return list(self._prices.keys())

    async def push_bar(self, bar: Bar) -> None:
        """Publishes a new bar: updates the current price, appends to bounded
        history, and wakes any active subscribe_live_data() consumers."""
        self._prices[bar.asset] = bar.close

        history = self._history[bar.asset]
        history.append(bar)
        if len(history) > self._history_limit:
            del history[: len(history) - self._history_limit]

        queue = self._queues.setdefault(bar.asset, asyncio.Queue())
        await queue.put(bar)

    async def stream(self, symbol: str) -> AsyncIterator[Bar]:
        queue = self._queues.setdefault(symbol, asyncio.Queue())
        while True:
            bar = await queue.get()
            yield bar
