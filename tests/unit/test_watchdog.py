from datetime import datetime, timedelta, timezone

import fakeredis
import pytest

from common import redis_keys
from engine.core.repository import InMemoryTradeRepository
from watchdog.heartbeat_watchdog import HeartbeatWatchdog

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


class RecordingAlertSink:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def send(self, message: str, priority: str = "critical") -> None:
        self.messages.append((message, priority))


def make_watchdog(timeout_seconds=300):
    redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    repo = InMemoryTradeRepository()
    sink = RecordingAlertSink()
    watchdog = HeartbeatWatchdog(
        redis_client, repo, alert_sink=sink, heartbeat_timeout_seconds=timeout_seconds, check_interval_seconds=5
    )
    return watchdog, redis_client, repo, sink


@pytest.mark.asyncio
async def test_healthy_heartbeat_does_not_trigger():
    watchdog, redis_client, repo, sink = make_watchdog()
    await redis_client.set(redis_keys.HEARTBEAT_KEY, T0.isoformat(), ex=15)

    triggered = await watchdog.check_once(T0)
    assert not triggered
    assert sink.messages == []


@pytest.mark.asyncio
async def test_missing_heartbeat_does_not_trigger_immediately():
    watchdog, redis_client, repo, sink = make_watchdog(timeout_seconds=300)
    triggered = await watchdog.check_once(T0)  # first-ever check, no heartbeat present
    assert not triggered


@pytest.mark.asyncio
async def test_brief_gap_does_not_trigger():
    watchdog, redis_client, repo, sink = make_watchdog(timeout_seconds=300)
    await redis_client.set(redis_keys.HEARTBEAT_KEY, T0.isoformat(), ex=15)
    await watchdog.check_once(T0)  # establishes last_healthy_at

    # Heartbeat key naturally expires (simulated by not writing again), but
    # only a few seconds have passed — well under the 300s timeout.
    await redis_client.delete(redis_keys.HEARTBEAT_KEY)
    triggered = await watchdog.check_once(T0 + timedelta(seconds=20))
    assert not triggered


@pytest.mark.asyncio
async def test_sustained_absence_triggers_emergency_flatten():
    watchdog, redis_client, repo, sink = make_watchdog(timeout_seconds=300)
    await redis_client.set(redis_keys.HEARTBEAT_KEY, T0.isoformat(), ex=15)
    await watchdog.check_once(T0)
    await redis_client.delete(redis_keys.HEARTBEAT_KEY)

    await repo.open_trade("strat_1", "paper1", "BTC/USD", "long", 10, T0, 100.0, 0.0)

    triggered = await watchdog.check_once(T0 + timedelta(seconds=301))
    assert triggered
    assert await repo.get_open_trades() == []  # emergency-closed

    safe_mode_hash = await redis_client.hgetall(redis_keys.STATE_SAFE_MODE)
    assert safe_mode_hash["triggered_by"] == "dead_man_switch"
    assert safe_mode_hash["requires_manual_restart"] == "True"

    events = repo.all_risk_events()
    assert any(e.event_type.value == "dead_man_switch" for e in events)
    assert len(sink.messages) == 2  # trigger alert + completion alert


@pytest.mark.asyncio
async def test_does_not_re_trigger_while_still_down():
    watchdog, redis_client, repo, sink = make_watchdog(timeout_seconds=300)
    await redis_client.set(redis_keys.HEARTBEAT_KEY, T0.isoformat(), ex=15)
    await watchdog.check_once(T0)
    await redis_client.delete(redis_keys.HEARTBEAT_KEY)

    await watchdog.check_once(T0 + timedelta(seconds=301))
    sink.messages.clear()

    triggered_again = await watchdog.check_once(T0 + timedelta(seconds=310))
    assert not triggered_again
    assert sink.messages == []


@pytest.mark.asyncio
async def test_re_arms_after_heartbeat_resumes():
    watchdog, redis_client, repo, sink = make_watchdog(timeout_seconds=300)
    await redis_client.set(redis_keys.HEARTBEAT_KEY, T0.isoformat(), ex=15)
    await watchdog.check_once(T0)
    await redis_client.delete(redis_keys.HEARTBEAT_KEY)
    await watchdog.check_once(T0 + timedelta(seconds=301))  # triggers

    # Engine comes back and resumes writing heartbeats.
    resumed_time = T0 + timedelta(seconds=400)
    await redis_client.set(redis_keys.HEARTBEAT_KEY, resumed_time.isoformat(), ex=15)
    triggered = await watchdog.check_once(resumed_time)
    assert not triggered

    # A second sustained outage after recovery should be able to trigger again.
    await redis_client.delete(redis_keys.HEARTBEAT_KEY)
    triggered_again = await watchdog.check_once(resumed_time + timedelta(seconds=301))
    assert triggered_again
