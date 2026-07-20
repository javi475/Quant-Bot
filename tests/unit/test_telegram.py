import json

import httpx
import pytest

from common.telegram import TelegramAlertService, format_alert


def test_format_alert_includes_emoji_title_and_separator():
    text = format_alert("engine down", "critical")
    assert "CRITICAL" in text
    assert "engine down" in text
    assert "—" * 28 in text


def test_format_alert_truncates_to_max_length():
    text = format_alert("x" * 5000, "info")
    assert len(text) <= 4096


def make_service(min_priority="info", capture=None):
    async def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return TelegramAlertService("bot-token", "chat-id", http_client, min_priority=min_priority)


@pytest.mark.asyncio
async def test_send_posts_to_telegram_api():
    captured = []
    service = make_service(capture=captured)
    sent = await service.send("engine down", priority="critical")

    assert sent
    assert len(captured) == 1
    request = captured[0]
    assert request.url.path == "/botbot-token/sendMessage"
    payload = json.loads(request.content)
    assert payload["chat_id"] == "chat-id"
    assert "engine down" in payload["text"]


@pytest.mark.asyncio
async def test_info_message_filtered_when_min_priority_is_warning():
    captured = []
    service = make_service(min_priority="warning", capture=captured)
    sent = await service.send("just fyi", priority="info")
    assert not sent
    assert captured == []


@pytest.mark.asyncio
async def test_critical_always_sent_regardless_of_min_priority():
    captured = []
    service = make_service(min_priority="critical", capture=captured)
    sent = await service.send("everything is fine", priority="info")
    assert not sent

    sent = await service.send("everything is on fire", priority="critical")
    assert sent
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_http_error_raises():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"ok": False})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    service = TelegramAlertService("bad-token", "chat-id", http_client)

    with pytest.raises(httpx.HTTPStatusError):
        await service.send("test", priority="critical")
