import json

import fakeredis
import httpx
import pytest

from common.redis_keys import SIGNAL_QUEUE
from engine.strategy.serialization import decode_signal
from webhook.app import create_app
from webhook.security import compute_signature

SECRET = "test-secret"


async def make_client():
    redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    app = create_app(redis_client, SECRET)
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://webhook-test")
    return client, redis_client


def sign(body: bytes) -> str:
    return compute_signature(SECRET, body)


@pytest.mark.asyncio
async def test_valid_signed_alert_is_queued():
    client, redis_client = await make_client()
    async with client:
        payload = {"strategy_id": "strat_tv", "asset": "BTC/USD", "direction": "long", "strength": 0.8}
        body = json.dumps(payload).encode()
        resp = await client.post(
            "/webhook/tradingview", content=body, headers={"X-TV-Signature": sign(body)}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    raw = await redis_client.lpop(SIGNAL_QUEUE)
    envelope = json.loads(raw)
    assert envelope["strategy_id"] == "strat_tv"
    signal = decode_signal(envelope["signal"])
    assert signal.asset == "BTC/USD"
    assert signal.strength == 0.8


@pytest.mark.asyncio
async def test_missing_signature_rejected():
    client, redis_client = await make_client()
    async with client:
        payload = {"strategy_id": "strat_tv", "asset": "BTC/USD", "direction": "long"}
        body = json.dumps(payload).encode()
        resp = await client.post("/webhook/tradingview", content=body)
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wrong_signature_rejected():
    client, redis_client = await make_client()
    async with client:
        payload = {"strategy_id": "strat_tv", "asset": "BTC/USD", "direction": "long"}
        body = json.dumps(payload).encode()
        resp = await client.post(
            "/webhook/tradingview", content=body, headers={"X-TV-Signature": "deadbeef"}
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_tampered_body_rejected():
    client, redis_client = await make_client()
    async with client:
        original = json.dumps({"strategy_id": "strat_tv", "asset": "BTC/USD", "direction": "long"}).encode()
        signature = sign(original)
        tampered = json.dumps({"strategy_id": "strat_tv", "asset": "ETH/USD", "direction": "long"}).encode()
        resp = await client.post(
            "/webhook/tradingview", content=tampered, headers={"X-TV-Signature": signature}
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_malformed_payload_rejected_after_signature_check():
    client, redis_client = await make_client()
    async with client:
        body = json.dumps({"strategy_id": "strat_tv"}).encode()  # missing required fields
        resp = await client.post(
            "/webhook/tradingview", content=body, headers={"X-TV-Signature": sign(body)}
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_invalid_direction_rejected():
    client, redis_client = await make_client()
    async with client:
        body = json.dumps({"strategy_id": "strat_tv", "asset": "BTC/USD", "direction": "sideways"}).encode()
        resp = await client.post(
            "/webhook/tradingview", content=body, headers={"X-TV-Signature": sign(body)}
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_out_of_range_strength_rejected():
    client, redis_client = await make_client()
    async with client:
        body = json.dumps(
            {"strategy_id": "strat_tv", "asset": "BTC/USD", "direction": "long", "strength": 5.0}
        ).encode()
        resp = await client.post(
            "/webhook/tradingview", content=body, headers={"X-TV-Signature": sign(body)}
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_schema_endpoint():
    client, _ = await make_client()
    async with client:
        resp = await client.get("/webhook/tradingview/schema")
        assert resp.status_code == 200
        assert "direction" in resp.json()
