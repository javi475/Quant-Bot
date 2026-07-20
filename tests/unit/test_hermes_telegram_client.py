import httpx
import pytest

from hermes.telegram_client import TelegramUpdatesClient

BOT_TOKEN = "test-token"


class FakeTelegramTransport(httpx.MockTransport):
    def __init__(self):
        self.get_updates_calls = []
        self.sent_messages = []
        self._batches = []
        super().__init__(self._handle)

    def queue_batch(self, updates):
        self._batches.append(updates)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getUpdates"):
            params = dict(httpx.QueryParams(request.url.query))
            self.get_updates_calls.append(params)
            batch = self._batches.pop(0) if self._batches else []
            return httpx.Response(200, json={"ok": True, "result": batch})
        if request.url.path.endswith("/sendMessage"):
            import json

            self.sent_messages.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True, "result": {}})
        return httpx.Response(404)


@pytest.fixture
def transport():
    return FakeTelegramTransport()


@pytest.fixture
def http_client(transport):
    return httpx.AsyncClient(transport=transport)


@pytest.mark.asyncio
async def test_get_updates_returns_batch(transport, http_client):
    transport.queue_batch([{"update_id": 1, "message": {"text": "/status"}}])
    client = TelegramUpdatesClient(BOT_TOKEN, http_client)

    updates = await client.get_updates()

    assert updates == [{"update_id": 1, "message": {"text": "/status"}}]
    await http_client.aclose()


@pytest.mark.asyncio
async def test_get_updates_advances_offset_across_calls(transport, http_client):
    transport.queue_batch([{"update_id": 5, "message": {}}, {"update_id": 6, "message": {}}])
    transport.queue_batch([])
    client = TelegramUpdatesClient(BOT_TOKEN, http_client)

    await client.get_updates()
    assert "offset" not in transport.get_updates_calls[0]

    await client.get_updates()
    assert transport.get_updates_calls[1]["offset"] == "7"

    await http_client.aclose()


@pytest.mark.asyncio
async def test_get_updates_offset_unchanged_when_no_updates(transport, http_client):
    transport.queue_batch([{"update_id": 10, "message": {}}])
    transport.queue_batch([])
    client = TelegramUpdatesClient(BOT_TOKEN, http_client)

    await client.get_updates()
    await client.get_updates()
    await client.get_updates()

    assert transport.get_updates_calls[1]["offset"] == "11"
    assert transport.get_updates_calls[2]["offset"] == "11"

    await http_client.aclose()


@pytest.mark.asyncio
async def test_send_message_posts_chat_id_and_text(transport, http_client):
    client = TelegramUpdatesClient(BOT_TOKEN, http_client)

    await client.send_message("12345", "hello operator")

    assert transport.sent_messages == [{"chat_id": "12345", "text": "hello operator"}]

    await http_client.aclose()
