from datetime import datetime, timedelta, timezone

import pytest

from hermes.client import HermesClientError
from hermes.commands import CONFIRMATION_WINDOW_SECONDS, HELP_TEXT, TelegramCommandHandler

CHAT_ID = "12345"
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeHermesClient:
    def __init__(self):
        self.halt_called = False
        self.flatten_called = False
        self.kill_called = False
        self.risk_set_calls = []
        self._status = {"equity": 100_000.0, "open_position_count": 1, "safe_mode": {"active": False}, "halted": False}
        self._positions = {"open_position_count": 1, "gross_exposure_value": 5000.0}
        self._risk_params = {"max_drawdown": 0.15, "kelly_multiplier": 0.25}
        self.raise_on_risk_set = None

    async def status(self):
        return self._status

    async def positions(self):
        return self._positions

    async def risk_get(self):
        return self._risk_params

    async def risk_set(self, updates):
        if self.raise_on_risk_set:
            raise self.raise_on_risk_set
        self.risk_set_calls.append(updates)
        self._risk_params.update(updates)
        return self._risk_params

    async def halt(self):
        self.halt_called = True
        return {"status": "halted"}

    async def flatten(self):
        self.flatten_called = True
        return {"status": "flattened"}

    async def kill(self):
        self.kill_called = True
        return {"status": "killed"}


def make_update(chat_id, text):
    return {"message": {"chat": {"id": chat_id}, "text": text}}


class Replies:
    def __init__(self):
        self.messages = []

    async def __call__(self, text):
        self.messages.append(text)


@pytest.fixture
def handler():
    return TelegramCommandHandler(FakeHermesClient(), CHAT_ID)


@pytest.mark.asyncio
async def test_unauthorized_chat_is_ignored(handler):
    reply = Replies()
    await handler.handle_update(make_update("99999", "/status"), reply, NOW)
    assert reply.messages == []


@pytest.mark.asyncio
async def test_non_command_text_is_ignored(handler):
    reply = Replies()
    await handler.handle_update(make_update(CHAT_ID, "hello there"), reply, NOW)
    assert reply.messages == []


@pytest.mark.asyncio
async def test_help_command(handler):
    reply = Replies()
    await handler.handle_update(make_update(CHAT_ID, "/help"), reply, NOW)
    assert reply.messages == [HELP_TEXT]


@pytest.mark.asyncio
async def test_status_command(handler):
    reply = Replies()
    await handler.handle_update(make_update(CHAT_ID, "/status"), reply, NOW)
    assert "Equity: $100,000.00" in reply.messages[0]
    assert "running" in reply.messages[0]


@pytest.mark.asyncio
async def test_positions_command(handler):
    reply = Replies()
    await handler.handle_update(make_update(CHAT_ID, "/positions"), reply, NOW)
    assert "Open positions: 1" in reply.messages[0]
    assert "$5,000.00" in reply.messages[0]


@pytest.mark.asyncio
async def test_risk_command(handler):
    reply = Replies()
    await handler.handle_update(make_update(CHAT_ID, "/risk"), reply, NOW)
    assert "kelly_multiplier: 0.25" in reply.messages[0]
    assert "max_drawdown: 0.15" in reply.messages[0]


@pytest.mark.asyncio
async def test_unknown_command(handler):
    reply = Replies()
    await handler.handle_update(make_update(CHAT_ID, "/frobnicate"), reply, NOW)
    assert "Unknown command" in reply.messages[0]


@pytest.mark.asyncio
async def test_unsupported_command_gives_reason(handler):
    reply = Replies()
    await handler.handle_update(make_update(CHAT_ID, "/proposal"), reply, NOW)
    assert "Not available yet" in reply.messages[0]


@pytest.mark.asyncio
async def test_cancel_with_nothing_pending(handler):
    reply = Replies()
    await handler.handle_update(make_update(CHAT_ID, "/cancel"), reply, NOW)
    assert reply.messages == ["Nothing pending to cancel."]


@pytest.mark.asyncio
async def test_confirm_with_nothing_pending(handler):
    reply = Replies()
    await handler.handle_update(make_update(CHAT_ID, "/confirm"), reply, NOW)
    assert reply.messages == ["Nothing pending to confirm."]


@pytest.mark.asyncio
async def test_halt_requires_confirmation_then_executes(handler):
    reply = Replies()
    await handler.handle_update(make_update(CHAT_ID, "/halt"), reply, NOW)
    assert "requires confirmation" in reply.messages[0]
    assert not handler.client.halt_called

    await handler.handle_update(make_update(CHAT_ID, "/confirm"), reply, NOW)
    assert handler.client.halt_called
    assert reply.messages[-1] == "Halted."


@pytest.mark.asyncio
async def test_destructive_command_can_be_cancelled(handler):
    reply = Replies()
    await handler.handle_update(make_update(CHAT_ID, "/flatten"), reply, NOW)
    await handler.handle_update(make_update(CHAT_ID, "/cancel"), reply, NOW)
    assert reply.messages[-1] == "Cancelled."
    assert not handler.client.flatten_called

    # Now confirm should find nothing pending since it was cancelled.
    await handler.handle_update(make_update(CHAT_ID, "/confirm"), reply, NOW)
    assert reply.messages[-1] == "Nothing pending to confirm."


@pytest.mark.asyncio
async def test_confirmation_expires_after_window(handler):
    reply = Replies()
    await handler.handle_update(make_update(CHAT_ID, "/kill"), reply, NOW)

    later = NOW + timedelta(seconds=CONFIRMATION_WINDOW_SECONDS + 1)
    await handler.handle_update(make_update(CHAT_ID, "/confirm"), reply, later)

    assert "expired" in reply.messages[-1]
    assert not handler.client.kill_called


@pytest.mark.asyncio
async def test_risk_set_valid_updates_param(handler):
    reply = Replies()
    await handler.handle_update(make_update(CHAT_ID, "/risk_set max_drawdown 0.20"), reply, NOW)
    await handler.handle_update(make_update(CHAT_ID, "/confirm"), reply, NOW)

    assert handler.client.risk_set_calls == [{"max_drawdown": 0.20}]
    assert "updated to 0.2" in reply.messages[-1]


@pytest.mark.asyncio
async def test_risk_set_wrong_arg_count(handler):
    reply = Replies()
    await handler.handle_update(make_update(CHAT_ID, "/risk_set max_drawdown"), reply, NOW)
    await handler.handle_update(make_update(CHAT_ID, "/confirm"), reply, NOW)
    assert reply.messages[-1] == "Usage: /risk_set <param> <value>"


@pytest.mark.asyncio
async def test_risk_set_non_numeric_value(handler):
    reply = Replies()
    await handler.handle_update(make_update(CHAT_ID, "/risk_set max_drawdown abc"), reply, NOW)
    await handler.handle_update(make_update(CHAT_ID, "/confirm"), reply, NOW)
    assert "valid number" in reply.messages[-1]


@pytest.mark.asyncio
async def test_execute_reports_client_error(handler):
    handler.client.raise_on_risk_set = HermesClientError("bad value", status_code=400)
    reply = Replies()
    await handler.handle_update(make_update(CHAT_ID, "/risk_set max_drawdown 99"), reply, NOW)
    await handler.handle_update(make_update(CHAT_ID, "/confirm"), reply, NOW)
    assert "Failed" in reply.messages[-1]
