from datetime import datetime, timezone

import fakeredis
import pytest

from hermes.memory import PersistentMemory
from hermes.scheduler import CronJob, CronScheduler

T0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def memory():
    return PersistentMemory(fakeredis.FakeAsyncRedis(decode_responses=True))


def always_due(now, last_run):
    return True


def never_due(now, last_run):
    return False


@pytest.mark.asyncio
async def test_due_job_runs_and_updates_last_run(memory):
    calls = []

    async def handler(now):
        calls.append(now)

    scheduler = CronScheduler(memory, [CronJob("job_a", always_due, handler)])
    ran = await scheduler.run_due_jobs(T0)

    assert ran == ["job_a"]
    assert calls == [T0]
    assert await memory.get_last_run("job_a") == T0


@pytest.mark.asyncio
async def test_non_due_job_is_skipped(memory):
    calls = []

    async def handler(now):
        calls.append(now)

    scheduler = CronScheduler(memory, [CronJob("job_a", never_due, handler)])
    ran = await scheduler.run_due_jobs(T0)

    assert ran == []
    assert calls == []
    assert await memory.get_last_run("job_a") is None


@pytest.mark.asyncio
async def test_one_job_failure_does_not_block_others(memory):
    calls = []

    async def failing_handler(now):
        raise RuntimeError("boom")

    async def ok_handler(now):
        calls.append(now)

    scheduler = CronScheduler(
        memory,
        [CronJob("failing", always_due, failing_handler), CronJob("ok", always_due, ok_handler)],
    )
    ran = await scheduler.run_due_jobs(T0)

    assert ran == ["ok"]
    assert calls == [T0]
    assert await memory.get_last_run("failing") is None
    assert await memory.get_last_run("ok") == T0


@pytest.mark.asyncio
async def test_multiple_due_jobs_all_run(memory):
    calls = []

    async def make_handler(name):
        async def handler(now):
            calls.append(name)

        return handler

    scheduler = CronScheduler(
        memory,
        [
            CronJob("job_a", always_due, await make_handler("a")),
            CronJob("job_b", always_due, await make_handler("b")),
        ],
    )
    ran = await scheduler.run_due_jobs(T0)

    assert ran == ["job_a", "job_b"]
    assert calls == ["a", "b"]


@pytest.mark.asyncio
async def test_defaults_now_to_current_time_when_omitted(memory):
    calls = []

    async def handler(now):
        calls.append(now)

    scheduler = CronScheduler(memory, [CronJob("job_a", always_due, handler)])
    await scheduler.run_due_jobs()

    assert len(calls) == 1
    assert calls[0].tzinfo is not None
