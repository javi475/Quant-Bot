from datetime import datetime, timedelta, timezone

import pytest

from common.enums import AssetClass, OrderSide, OrderStatus, OrderType, Timeframe
from engine.backtest.cost_model import TransactionCostModel
from engine.connectors.base import ConnectorError
from engine.connectors.paper import PaperConnector
from engine.connectors.price_feed import ReplayPriceFeed
from engine.models.order import Order
from sdk.ate_smp.models.bar import Bar

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_connector(initial_capital=100_000.0, spread_bps=10.0, cost_model=None):
    feed = ReplayPriceFeed()
    connector = PaperConnector(
        connector_id="paper1",
        asset_class=AssetClass.CRYPTO,
        feed=feed,
        cost_model=cost_model or TransactionCostModel(),
        initial_capital=initial_capital,
        spread_bps=spread_bps,
    )
    return connector, feed


@pytest.mark.asyncio
async def test_connect_lifecycle():
    connector, _ = make_connector()
    assert not connector.is_connected()
    await connector.connect({})
    assert connector.is_connected()
    await connector.disconnect()
    assert not connector.is_connected()


@pytest.mark.asyncio
async def test_get_live_quote_uses_spread():
    connector, feed = make_connector(spread_bps=100.0)  # 1% total spread
    feed.set_price("BTC/USD", 100.0)
    quote = await connector.get_live_quote("BTC/USD")
    assert quote.bid < 100.0 < quote.ask
    assert quote.ask - quote.bid == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_get_live_quote_raises_without_price():
    connector, _ = make_connector()
    with pytest.raises(ConnectorError):
        await connector.get_live_quote("BTC/USD")


@pytest.mark.asyncio
async def test_market_buy_fills_immediately_and_moves_cash():
    connector, feed = make_connector(initial_capital=100_000, spread_bps=0.0)
    await connector.connect({})
    feed.set_price("BTC/USD", 100.0)

    order = Order(asset="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    filled = await connector.place_order(order)

    assert filled.status == OrderStatus.FILLED
    assert filled.metadata["fill_price"] == pytest.approx(100.0)
    assert connector.cash == pytest.approx(100_000 - 1000)

    position = await connector.get_position("BTC/USD")
    assert position.quantity == pytest.approx(10)
    assert position.entry_price == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_market_sell_closes_long_position():
    connector, feed = make_connector(spread_bps=0.0)
    await connector.connect({})
    feed.set_price("BTC/USD", 100.0)
    await connector.place_order(Order(asset="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10))

    feed.set_price("BTC/USD", 110.0)
    sell = await connector.place_order(Order(asset="BTC/USD", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=10))

    assert sell.metadata["fill_price"] == pytest.approx(110.0)
    assert await connector.get_position("BTC/USD") is None
    # cash: -1000 (entry) + 1100 (exit) = 100 profit above initial capital
    assert connector.cash == pytest.approx(100_000 + 100)


@pytest.mark.asyncio
async def test_short_sell_and_cover():
    connector, feed = make_connector(spread_bps=0.0)
    await connector.connect({})
    feed.set_price("BTC/USD", 100.0)
    await connector.place_order(Order(asset="BTC/USD", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=5))

    position = await connector.get_position("BTC/USD")
    assert position.quantity == pytest.approx(-5)

    feed.set_price("BTC/USD", 90.0)  # price drops, short profits
    await connector.place_order(Order(asset="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=5))
    assert await connector.get_position("BTC/USD") is None
    assert connector.cash == pytest.approx(100_000 + 50)  # (100-90)*5


@pytest.mark.asyncio
async def test_limit_order_marketable_fills_immediately():
    connector, feed = make_connector(spread_bps=0.0)
    await connector.connect({})
    feed.set_price("BTC/USD", 100.0)
    order = Order(asset="BTC/USD", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=1, limit_price=101.0)
    filled = await connector.place_order(order)
    assert filled.status == OrderStatus.FILLED
    assert filled.metadata["fill_price"] == pytest.approx(101.0)


@pytest.mark.asyncio
async def test_limit_order_not_marketable_stays_pending_then_fills():
    connector, feed = make_connector(spread_bps=0.0)
    await connector.connect({})
    feed.set_price("BTC/USD", 100.0)
    order = Order(asset="BTC/USD", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=1, limit_price=95.0)
    placed = await connector.place_order(order)
    assert placed.status == OrderStatus.OPEN

    fills = await connector.process_pending_orders()
    assert fills == []  # price hasn't crossed yet

    feed.set_price("BTC/USD", 94.0)  # now marketable
    fills = await connector.process_pending_orders()
    assert len(fills) == 1
    assert fills[0].price == pytest.approx(95.0)  # limit orders fill at their own price


@pytest.mark.asyncio
async def test_cancel_pending_order():
    connector, feed = make_connector(spread_bps=0.0)
    await connector.connect({})
    feed.set_price("BTC/USD", 100.0)
    order = Order(asset="BTC/USD", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=1, limit_price=95.0)
    placed = await connector.place_order(order)

    await connector.cancel_order(placed.venue_order_id)
    status = await connector.get_order_status(placed.venue_order_id)
    assert status.status == OrderStatus.CANCELLED

    with pytest.raises(ConnectorError):
        await connector.cancel_order(placed.venue_order_id)


@pytest.mark.asyncio
async def test_modify_pending_order():
    connector, feed = make_connector(spread_bps=0.0)
    await connector.connect({})
    feed.set_price("BTC/USD", 100.0)
    order = Order(asset="BTC/USD", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=1, limit_price=95.0)
    placed = await connector.place_order(order)

    modified = await connector.modify_order(placed.venue_order_id, quantity=2, limit_price=96.0)
    assert modified.quantity == 2
    assert modified.limit_price == 96.0


@pytest.mark.asyncio
async def test_get_order_status_unknown_raises():
    connector, _ = make_connector()
    with pytest.raises(ConnectorError):
        await connector.get_order_status("nonexistent")


@pytest.mark.asyncio
async def test_fees_reduce_cash_on_fill():
    connector, feed = make_connector(
        spread_bps=0.0, cost_model=TransactionCostModel(taker_fee=0.01)
    )
    await connector.connect({})
    feed.set_price("BTC/USD", 100.0)
    await connector.place_order(Order(asset="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10))
    # notional 1000, fee 1% = 10
    assert connector.cash == pytest.approx(100_000 - 1000 - 10)


@pytest.mark.asyncio
async def test_get_historical_bars_reads_from_feed_history():
    connector, feed = make_connector()
    bars = [
        Bar(asset="BTC/USD", timeframe=Timeframe.H1, timestamp=T0 + timedelta(hours=i),
            open=100, high=101, low=99, close=100, volume=1)
        for i in range(5)
    ]
    for bar in bars:
        await feed.push_bar(bar)

    result = await connector.get_historical_bars("BTC/USD", Timeframe.H1, T0, T0 + timedelta(hours=2))
    assert len(result) == 3


@pytest.mark.asyncio
async def test_subscribe_live_data_rejects_multi_symbol():
    connector, _ = make_connector()
    with pytest.raises(ValueError):
        async for _ in connector.subscribe_live_data(["BTC/USD", "ETH/USD"], Timeframe.H1):
            pass


def test_capabilities_and_fee_schedule_sync_parts():
    connector, _ = make_connector()
    caps = connector.get_capabilities()
    assert caps.supports_short is True
    assert caps.supports_limit is True
    assert connector.get_supported_assets() == ["*"]


@pytest.mark.asyncio
async def test_get_fee_schedule():
    connector, _ = make_connector(cost_model=TransactionCostModel(maker_fee=0.001, taker_fee=0.002))
    schedule = await connector.get_fee_schedule()
    assert schedule == {"maker": 0.001, "taker": 0.002}
