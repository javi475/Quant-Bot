"""Dead-man-switch heartbeat writer (DOC 4 §5). Writes to Redis with a TTL
several times the write interval, so a crashed/hung Engine's key naturally
expires — the independent Watchdog process (watchdog/heartbeat_watchdog.py)
is what actually decides when a missing heartbeat means "act now" vs. "just a
transient blip," using the longer heartbeat_timeout_seconds window.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from common import redis_keys


class HeartbeatWriter:
    def __init__(
        self,
        redis_client: Any,
        interval_seconds: int = redis_keys.HEARTBEAT_TTL_SECONDS // 3,
        ttl_seconds: int = redis_keys.HEARTBEAT_TTL_SECONDS,
    ) -> None:
        self.redis = redis_client
        self.interval = timedelta(seconds=interval_seconds)
        self.ttl_seconds = ttl_seconds
        self._last_write: Optional[datetime] = None

    async def maybe_write(self, now: datetime) -> bool:
        """Writes only if the throttle interval has elapsed; returns whether
        a write happened."""
        if self._last_write is not None and (now - self._last_write) < self.interval:
            return False
        await self.force_write(now)
        return True

    async def force_write(self, now: datetime) -> None:
        await self.redis.set(redis_keys.HEARTBEAT_KEY, now.isoformat(), ex=self.ttl_seconds)
        self._last_write = now
