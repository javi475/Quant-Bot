import asyncio
import json
from datetime import datetime, timezone

import fakeredis
import pytest

from common.enums import AssetClass, Direction, Timeframe
from common.redis_keys import SIGNAL_QUEUE
from engine.connectors.paper import PaperConnector
from engine.connectors.price_feed import ReplayPriceFeed
from engine.core.signal_scheduler import SignalScheduler
from engine.strategy.serialization import encode_signal
from sdk.ate_smp.models.bar import Bar
from sdk.ate_smp.models.signal import Signal

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def _pump() -> None:
    """Lets background subscription-consumer tasks run before assertions."""
    for _ in range(3):
        await asyncio.sleep(0)


def make_bar(asset: str, close: float) -> Bar:
    return Bar(
        asset=asset, timeframe=Timeframe.H1, timestamp=T0,
        open=close, high=close + 0.5, low=close - 0.5, close=close, volume=1.0,
    )


@pytest.mark.asyncio
async def test_drain_bars_empty_when_nothing_subscribed():
    scheduler = SignalScheduler()
    assert scheduler.drain_bars() == {}


@pytest.mark.asyncio
async def test_subscribe_and_drain_bars():
    feed = ReplayPriceFeed()
    connector = PaperConnector("paper1", AssetClass.CRYPTO, feed)
    await connector.connect({})

    scheduler = SignalScheduler()
    scheduler.subscribe(connector, "BTC/USD", Timeframe.H1)

    await feed.push_bar(make_bar("BTC/USD", 100.0))
    await feed.push_bar(make_bar("BTC/USD", 101.0))
    await _pump()

    drained = scheduler.drain_bars()
    assert len(drained["BTC/USD"]) == 2
    assert drained["BTC/USD"][0].close == 100.0

    # Draining again returns nothing new until more bars arrive.
    assert scheduler.drain_bars() == {}

    await scheduler.stop_all()


@pytest.mark.asyncio
async def test_subscribe_is_idempotent():
    feed = ReplayPriceFeed()
    connector = PaperConnector("paper1", AssetClass.CRYPTO, feed)
    await connector.connect({})

    scheduler = SignalScheduler()
    scheduler.subscribe(connector, "BTC/USD", Timeframe.H1)
    scheduler.subscribe(connector, "BTC/USD", Timeframe.H1)  # no-op, no duplicate task
    assert len(scheduler._tasks) == 1
    await scheduler.stop_all()


@pytest.mark.asyncio
async def test_unsubscribe_stops_consuming():
    feed = ReplayPriceFeed()
    connector = PaperConnector("paper1", AssetClass.CRYPTO, feed)
    await connector.connect({})

    scheduler = SignalScheduler()
    scheduler.subscribe(connector, "BTC/USD", Timeframe.H1)
    await _pump()
    scheduler.unsubscribe("paper1", "BTC/USD")

    await feed.push_bar(make_bar("BTC/USD", 100.0))
    await _pump()
    assert scheduler.drain_bars() == {}


@pytest.mark.asyncio
async def test_drain_webhook_signals_pops_everything():
    redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    signal = Signal(timestamp=T0, asset="BTC/USD", direction=Direction.LONG, strength=0.8)
    envelope = json.dumps({"strategy_id": "strat_tv", "signal": encode_signal(signal)})
    await redis_client.rpush(SIGNAL_QUEUE, envelope)
    await redis_client.rpush(SIGNAL_QUEUE, envelope)

    scheduler = SignalScheduler()
    results = await scheduler.drain_webhook_signals(redis_client)

    assert len(results) == 2
    strategy_id, decoded_signal = results[0]
    assert strategy_id == "strat_tv"
    assert decoded_signal.asset == "BTC/USD"
    assert decoded_signal.direction == Direction.LONG

    # Queue is now empty.
    assert await scheduler.drain_webhook_signals(redis_client) == []


@pytest.mark.asyncio
async def test_drain_webhook_signals_skips_malformed_payloads():
    redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    await redis_client.rpush(SIGNAL_QUEUE, "not json")
    await redis_client.rpush(SIGNAL_QUEUE, json.dumps({"strategy_id": "strat_1"}))  # missing "signal"

    scheduler = SignalScheduler()
    results = await scheduler.drain_webhook_signals(redis_client)
    assert results == []
