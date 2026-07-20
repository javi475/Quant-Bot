from datetime import datetime, timezone

import fakeredis
import pytest

from hermes.app import HermesApp
from hermes.commands import TelegramCommandHandler
from hermes.memory import PersistentMemory

CHAT_ID = "12345"
NOW = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)


class FakeHermesClient:
    async def status(self):
        return {"equity": 100_000.0, "open_position_count": 0, "safe_mode": {"active": False}, "halted": False}

    async def positions(self):
        return {"open_position_count": 0, "gross_exposure_value": 0.0, "equity": 100_000.0}

    async def risk_get(self):
        return {"max_drawdown": 0.15}

    async def risk_set(self, updates):
        return updates

    async def trades(self, strategy_id=None):
        return {"trades": []}

    async def halt(self):
        return {"status": "halted"}

    async def flatten(self):
        return {"status": "flattened"}

    async def kill(self):
        return {"status": "killed"}


class RecordingAlertSink:
    def __init__(self):
        self.sent = []

    async def send(self, message, priority="critical"):
        self.sent.append((message, priority))


class FakeUpdatesClient:
    def __init__(self, batches=None):
        self._batches = batches or []
        self.sent_messages = []

    async def get_updates(self):
        return self._batches.pop(0) if self._batches else []

    async def send_message(self, chat_id, text):
        self.sent_messages.append((chat_id, text))


@pytest.fixture
def memory():
    return PersistentMemory(fakeredis.FakeAsyncRedis(decode_responses=True))


@pytest.mark.asyncio
async def test_tick_runs_due_cron_jobs(memory):
    client = FakeHermesClient()
    sink = RecordingAlertSink()
    app = HermesApp(client, memory, sink)

    ran = await app.tick(NOW)

    # health_check (every 5 min) and midday_status (daily 12:00 - not due at 08:00) etc.
    assert "health_check" in ran
    assert "midday_status" not in ran


@pytest.mark.asyncio
async def test_tick_does_not_rerun_job_already_run_this_tick_window(memory):
    client = FakeHermesClient()
    sink = RecordingAlertSink()
    app = HermesApp(client, memory, sink)

    first = await app.tick(NOW)
    second = await app.tick(NOW)

    assert "health_check" in first
    assert "health_check" not in second


@pytest.mark.asyncio
async def test_tick_without_telegram_wiring_skips_command_handling(memory):
    client = FakeHermesClient()
    sink = RecordingAlertSink()
    app = HermesApp(client, memory, sink)

    await app.tick(NOW)  # should not raise despite no command_handler/updates_client


@pytest.mark.asyncio
async def test_tick_drains_and_handles_telegram_updates(memory):
    client = FakeHermesClient()
    sink = RecordingAlertSink()
    command_handler = TelegramCommandHandler(client, CHAT_ID)
    updates_client = FakeUpdatesClient(
        batches=[[{"message": {"chat": {"id": int(CHAT_ID)}, "text": "/status"}}]]
    )
    app = HermesApp(client, memory, sink, command_handler=command_handler, updates_client=updates_client)

    await app.tick(NOW)

    assert len(updates_client.sent_messages) == 1
    chat_id, text = updates_client.sent_messages[0]
    assert chat_id == CHAT_ID
    assert "Equity" in text


@pytest.mark.asyncio
async def test_tick_ignores_updates_from_unauthorized_chat(memory):
    client = FakeHermesClient()
    sink = RecordingAlertSink()
    command_handler = TelegramCommandHandler(client, CHAT_ID)
    updates_client = FakeUpdatesClient(batches=[[{"message": {"chat": {"id": 99999}, "text": "/status"}}]])
    app = HermesApp(client, memory, sink, command_handler=command_handler, updates_client=updates_client)

    await app.tick(NOW)

    assert updates_client.sent_messages == []


def test_stop_flips_running_flag():
    client = FakeHermesClient()
    sink = RecordingAlertSink()
    memory = PersistentMemory(fakeredis.FakeAsyncRedis(decode_responses=True))
    app = HermesApp(client, memory, sink)

    app._running = True
    app.stop()

    assert app._running is False
