from datetime import datetime, timezone

import fakeredis
import pytest

from hermes.memory import LAST_DAILY_REPORT, MAX_HISTORY_LENGTH, PersistentMemory

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def memory():
    return PersistentMemory(fakeredis.FakeAsyncRedis(decode_responses=True))


@pytest.mark.asyncio
async def test_last_run_roundtrip_named_key(memory):
    assert await memory.get_last_run("daily_report") is None
    await memory.set_last_run("daily_report", T0)
    assert await memory.get_last_run("daily_report") == T0
    assert await memory.redis.get(LAST_DAILY_REPORT) == T0.isoformat()


@pytest.mark.asyncio
async def test_last_run_roundtrip_generic_key(memory):
    await memory.set_last_run("health_check", T0)
    assert await memory.get_last_run("health_check") == T0
    assert await memory.redis.get("hermes:last_run:health_check") == T0.isoformat()


@pytest.mark.asyncio
async def test_generic_json_roundtrip(memory):
    assert await memory.get_json("some_key") is None
    await memory.set_json("some_key", {"a": 1, "b": [1, 2, 3]})
    assert await memory.get_json("some_key") == {"a": 1, "b": [1, 2, 3]}


@pytest.mark.asyncio
async def test_json_with_ttl_expires():
    redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    memory = PersistentMemory(redis_client)
    await memory.set_json("temp_key", {"x": 1}, ttl_seconds=100)
    ttl = await redis_client.ttl("temp_key")
    assert 0 < ttl <= 100


@pytest.mark.asyncio
async def test_append_history_grows_and_bounds(memory):
    for i in range(5):
        await memory.append_history("hist", {"i": i}, ttl_seconds=3600)
    history = await memory.get_json("hist")
    assert len(history) == 5
    assert history[-1] == {"i": 4}


@pytest.mark.asyncio
async def test_append_history_respects_max_length(memory):
    for i in range(10):
        await memory.append_history("hist", {"i": i}, ttl_seconds=3600, max_length=3)
    history = await memory.get_json("hist")
    assert len(history) == 3
    assert [h["i"] for h in history] == [7, 8, 9]


@pytest.mark.asyncio
async def test_record_risk_event_connector_health_system_metrics(memory):
    await memory.record_risk_event({"type": "daily_loss_breaker"})
    await memory.record_connector_health({"connector": "paper1", "healthy": True})
    await memory.record_system_metrics({"equity": 100000})

    assert len(await memory.get_json("hermes:risk_event_history")) == 1
    assert len(await memory.get_json("hermes:connector_health_history")) == 1
    assert len(await memory.get_json("hermes:system_metrics_history")) == 1


@pytest.mark.asyncio
async def test_safe_mode_alert_dedup(memory):
    assert not await memory.has_alerted_safe_mode("daily_loss_breaker", "entry_block")
    await memory.mark_safe_mode_alerted("daily_loss_breaker", "entry_block")
    assert await memory.has_alerted_safe_mode("daily_loss_breaker", "entry_block")
    # A different phase/trigger is a distinct episode.
    assert not await memory.has_alerted_safe_mode("daily_loss_breaker", "recovery")
    assert not await memory.has_alerted_safe_mode("drawdown_ceiling", "entry_block")


@pytest.mark.asyncio
async def test_clear_safe_mode_alert(memory):
    await memory.mark_safe_mode_alerted("daily_loss_breaker", "entry_block")
    await memory.clear_safe_mode_alert()
    assert not await memory.has_alerted_safe_mode("daily_loss_breaker", "entry_block")


@pytest.mark.asyncio
async def test_proposal_tracking_roundtrip(memory):
    assert await memory.get_proposal_approved("prop_1") is None
    await memory.set_proposal_approved("prop_1", {"approved_by": "operator"})
    assert await memory.get_proposal_approved("prop_1") == {"approved_by": "operator"}

    await memory.set_proposal_outcome("prop_1", {"result": "improved"})
    assert await memory.get_proposal_outcome("prop_1") == {"result": "improved"}
