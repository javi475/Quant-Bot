"""Independent dead-man-switch process (DOC 4 §5). Runs as its own OS process
(systemd `ate-smp-watchdog.service` at deployment) so it survives an Engine
crash or hang — which also means it shares no memory with the Engine, and can
only act through things the Engine itself persisted: the Redis heartbeat key
and the TradeRepository's cold state.

For real venue connectors (M6), the watchdog would ALSO call each venue's
REST API directly to cancel orders and market-close positions — that's the
literal "bypass the Engine" action DOC 4 describes, and it works because a
real venue is an independent network service. PaperConnector has no existence
outside the Engine process's memory, so for paper mode the equivalent action
is: mark every open trade in the repository closed (at its own entry price —
a conservative, no-further-movement assumption, since we have no live price
reference while the Engine is down) and flip safe mode on directly in Redis
so the Engine picks it up the moment it restarts.

A missing heartbeat key alone does NOT trigger anything — Redis TTL expiry
(15s) is just a short-lived liveness signal that can blip from a GC pause or
a deploy restart. Only a *sustained* absence (>= heartbeat_timeout_seconds,
default 300s) trips the switch, per DOC 5 §7's noted "false dead-man trigger"
pitfall.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol

import structlog

from common import redis_keys
from common.enums import RiskEventSeverity, RiskEventType
from engine.core.repository import RiskEventRecord, TradeRepository

log = structlog.get_logger(service="watchdog")

DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 300
DEFAULT_CHECK_INTERVAL_SECONDS = 5


class AlertSink(Protocol):
    async def send(self, message: str, priority: str = "critical") -> None: ...


class LoggingAlertSink:
    """Placeholder alert sink until Hermes/Telegram lands (M5) — logs at
    critical level so nothing is silently swallowed in the meantime."""

    async def send(self, message: str, priority: str = "critical") -> None:
        log.critical("watchdog_alert", message=message, priority=priority)


class HeartbeatWatchdog:
    def __init__(
        self,
        redis_client: Any,
        repository: TradeRepository,
        alert_sink: Optional[AlertSink] = None,
        heartbeat_timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
        check_interval_seconds: int = DEFAULT_CHECK_INTERVAL_SECONDS,
    ) -> None:
        self.redis = redis_client
        self.repository = repository
        self.alert_sink = alert_sink or LoggingAlertSink()
        self.heartbeat_timeout = timedelta(seconds=heartbeat_timeout_seconds)
        self.check_interval_seconds = check_interval_seconds
        self._last_healthy_at: Optional[datetime] = None
        self._triggered = False

    async def check_once(self, now: Optional[datetime] = None) -> bool:
        """Runs a single liveness check. Returns True iff it triggered the
        emergency flatten this call."""
        now = now or datetime.now(timezone.utc)
        heartbeat = await self.redis.get(redis_keys.HEARTBEAT_KEY)

        if heartbeat is not None:
            self._last_healthy_at = now
            self._triggered = False
            return False

        if self._last_healthy_at is None:
            # First check ever with no heartbeat present: start the clock
            # rather than assuming an instant failure.
            self._last_healthy_at = now
            return False

        if self._triggered:
            return False  # already handled; wait for a heartbeat to resume before re-arming

        if now - self._last_healthy_at >= self.heartbeat_timeout:
            self._triggered = True
            await self._emergency_flatten(now)
            return True

        return False

    async def _emergency_flatten(self, now: datetime) -> None:
        await self.alert_sink.send(
            f"DEAD-MAN SWITCH TRIGGERED: no Engine heartbeat for >= {self.heartbeat_timeout}. "
            "Flattening all known open positions.",
            priority="critical",
        )

        open_trades = await self.repository.get_open_trades()
        for trade in open_trades:
            await self.repository.close_trade(trade.trade_id, now, trade.entry_price, 0.0)

        await self.redis.hset(
            redis_keys.STATE_SAFE_MODE,
            mapping={
                "phase": "entry_block",
                "triggered_by": RiskEventType.DEAD_MAN_SWITCH.value,
                "halt_new_entries": "True",
                "requires_manual_restart": "True",
            },
        )
        await self.redis.expire(redis_keys.STATE_SAFE_MODE, redis_keys.SAFE_MODE_TTL_SECONDS)

        await self.repository.record_risk_event(
            RiskEventRecord(
                event_type=RiskEventType.DEAD_MAN_SWITCH,
                severity=RiskEventSeverity.CRITICAL,
                description=f"No Engine heartbeat for >= {self.heartbeat_timeout}",
                action_taken=f"closed {len(open_trades)} open trade(s); safe mode activated",
                safe_mode_activated=True,
                occurred_at=now,
            )
        )

        await self.alert_sink.send(
            f"Emergency flatten complete: closed {len(open_trades)} trade(s). "
            "Engine is in 48h safe mode pending manual restart.",
            priority="critical",
        )

    async def run_forever(self) -> None:
        while True:
            await self.check_once()
            await asyncio.sleep(self.check_interval_seconds)


if __name__ == "__main__":  # pragma: no cover - deployment entrypoint
    import os

    async def main() -> None:
        import redis.asyncio as redis_asyncio

        redis_client = redis_asyncio.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True
        )
        raise NotImplementedError(
            "Standalone deployment wiring (a real Postgres-backed TradeRepository, "
            "Telegram AlertSink) lands with M6 deployment work; this entrypoint is a "
            "placeholder until then."
        )

    asyncio.run(main())
