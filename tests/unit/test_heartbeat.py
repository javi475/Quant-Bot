from datetime import datetime, timedelta, timezone

import fakeredis
import pytest

from common import redis_keys
from engine.core.heartbeat import HeartbeatWriter

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_force_write_sets_key_with_ttl():
    redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    writer = HeartbeatWriter(redis_client, interval_seconds=5, ttl_seconds=15)

    await writer.force_write(T0)

    assert await redis_client.get(redis_keys.HEARTBEAT_KEY) == T0.isoformat()
    ttl = await redis_client.ttl(redis_keys.HEARTBEAT_KEY)
    assert 0 < ttl <= 15


@pytest.mark.asyncio
async def test_maybe_write_throttles_within_interval():
    redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    writer = HeartbeatWriter(redis_client, interval_seconds=5, ttl_seconds=15)

    assert await writer.maybe_write(T0) is True
    assert await writer.maybe_write(T0 + timedelta(seconds=1)) is False  # too soon


@pytest.mark.asyncio
async def test_maybe_write_fires_again_after_interval():
    redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    writer = HeartbeatWriter(redis_client, interval_seconds=5, ttl_seconds=15)

    await writer.maybe_write(T0)
    fired = await writer.maybe_write(T0 + timedelta(seconds=6))
    assert fired is True
    assert await redis_client.get(redis_keys.HEARTBEAT_KEY) == (T0 + timedelta(seconds=6)).isoformat()
