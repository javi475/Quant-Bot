"""Bridges two signal sources into the Engine's per-cycle pipeline (DOC 2 §2.4
"Signal Scheduler"):

1. Subprocess-backed Python strategies get bars pushed to them via on_bar()
   (handled by the caller, AlgorithmEngine) — this class just supplies the
   bars, by running one background task per (connector, symbol, timeframe)
   subscription that drains a connector's `subscribe_live_data` async
   generator into a plain queue `run_cycle()` can pull from without blocking.

2. TradingView-driven "strategies" have no subprocess; their signals arrive
   out-of-band via the webhook receiver pushing onto the Redis
   `engine:signal_queue` list. `drain_webhook_signals()` pops everything
   currently queued each cycle.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from common.redis_keys import SIGNAL_QUEUE
from engine.connectors.base import ConnectorBase
from engine.strategy import serialization as ser
from sdk.ate_smp.models.bar import Bar
from sdk.ate_smp.models.signal import Signal


class SignalScheduler:
    def __init__(self) -> None:
        self._queues: dict[tuple[str, str], asyncio.Queue[Bar]] = {}
        self._tasks: dict[tuple[str, str], asyncio.Task] = {}

    def subscribe(self, connector: ConnectorBase, symbol: str, timeframe) -> None:
        key = (connector.connector_id, symbol)
        if key in self._tasks:
            return  # already subscribed

        queue: asyncio.Queue[Bar] = asyncio.Queue()
        self._queues[key] = queue

        async def _consume() -> None:
            async for bar in connector.subscribe_live_data([symbol], timeframe):
                await queue.put(bar)

        self._tasks[key] = asyncio.create_task(_consume())

    def unsubscribe(self, connector_id: str, symbol: str) -> None:
        key = (connector_id, symbol)
        task = self._tasks.pop(key, None)
        if task is not None:
            task.cancel()
        self._queues.pop(key, None)

    def drain_bars(self) -> dict[str, list[Bar]]:
        """Non-blocking drain of every subscription's queue, keyed by symbol."""
        drained: dict[str, list[Bar]] = {}
        for (_connector_id, symbol), queue in self._queues.items():
            bars: list[Bar] = []
            while True:
                try:
                    bars.append(queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            if bars:
                drained.setdefault(symbol, []).extend(bars)
        return drained

    async def drain_webhook_signals(self, redis_client: Any) -> list[tuple[str, Signal]]:
        """Pops every currently queued TradingView-originated signal from
        Redis. Envelope pushed by webhook/app.py: {"strategy_id": ..., "signal": {...}}."""
        results: list[tuple[str, Signal]] = []
        while True:
            raw = await redis_client.lpop(SIGNAL_QUEUE)
            if raw is None:
                break
            try:
                envelope = json.loads(raw)
                strategy_id = envelope["strategy_id"]
                signal = ser.decode_signal(envelope["signal"])
            except (KeyError, ValueError, TypeError):
                continue  # malformed payload: drop and continue draining
            results.append((strategy_id, signal))
        return results

    async def stop_all(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        for task in self._tasks.values():
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks.clear()
        self._queues.clear()
