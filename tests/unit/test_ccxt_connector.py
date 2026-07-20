"""Tests the connector's own translation/bookkeeping/error-handling logic
against a hand-rolled fake exchange object shaped like ccxt's async API —
no real network or credentials involved. See ccxt_connector.py's module
docstring for why this connector isn't exercised against a live exchange
this session."""

import asyncio
import itertools

import pytest

from common.enums import AssetClass, OrderSide, OrderStatus, OrderType, Timeframe
from engine.connectors.base import ConnectorError
from engine.connectors.ccxt_connector import CCXTConnector
from engine.models.order import Order


class FakeExchange:
    def __init__(self):
        self.has = {"editOrder": False, "createLimitOrder": True, "createStopOrder": False}
        self.fees = {"trading": {"maker": 0.001, "taker": 0.0015}}
        self.symbols = ["BTC/USDT", "ETH/USDT"]
        self._next_id = itertools.count(1)
        self._orders: dict[str, dict] = {}
        self._balance = {"free": {"USDT": 10_000.0}, "used": {}, "total": {"USDT": 10_000.0}}
        self._ohlcv: list[list] = []
        self._ticker = {"bid": 99.5, "ask": 100.5, "last": 100.0, "timestamp": 1_700_000_000_000}
        self.closed = False
        self.load_markets_called = False
        self.create_order_calls: list[tuple] = []
        self.cancel_order_calls: list[tuple] = []
        self.fetch_order_should_raise = False

    async def load_markets(self):
        self.load_markets_called = True

    async def fetch_ohlcv(self, symbol, timeframe=None, since=None, limit=None):
        candles = [c for c in self._ohlcv if since is None or c[0] >= since]
        return candles[:limit] if limit else candles

    async def fetch_ticker(self, symbol):
        return dict(self._ticker)

    async def create_order(self, symbol, type_, side, amount, price=None, params=None):
        self.create_order_calls.append((symbol, type_, side, amount, price, params))
        order_id = str(next(self._next_id))
        order = {
            "id": order_id, "status": "closed", "filled": amount,
            "average": price or self._ticker["last"], "fee": {"cost": 1.0},
        }
        self._orders[order_id] = order
        return order

    async def cancel_order(self, order_id, symbol=None):
        self.cancel_order_calls.append((order_id, symbol))
        if order_id in self._orders:
            self._orders[order_id]["status"] = "canceled"

    async def fetch_order(self, order_id, symbol=None):
        if self.fetch_order_should_raise or order_id not in self._orders:
            raise RuntimeError(f"no such order {order_id}")
        return dict(self._orders[order_id])

    async def edit_order(self, order_id, symbol, type_, side, amount, price=None):
        new_id = str(next(self._next_id))
        order = {"id": new_id, "status": "open", "filled": 0.0, "average": None}
        self._orders[new_id] = order
        return order

    async def fetch_balance(self):
        return dict(self._balance)

    async def close(self):
        self.closed = True


def make_connector(exchange=None, quote_currency="USDT"):
    exchange = exchange or FakeExchange()
    connector = CCXTConnector("ccxt1", "binance", AssetClass.CRYPTO, exchange=exchange, quote_currency=quote_currency)
    return connector, exchange


@pytest.mark.asyncio
async def test_connect_calls_load_markets_and_sets_connected():
    connector, exchange = make_connector()
    await connector.connect({"api_key": "k", "api_secret": "s"})
    assert exchange.load_markets_called
    assert connector.is_connected()


@pytest.mark.asyncio
async def test_disconnect_closes_exchange_and_sets_disconnected():
    connector, exchange = make_connector()
    await connector.connect({})
    await connector.disconnect()
    assert exchange.closed
    assert not connector.is_connected()


@pytest.mark.asyncio
async def test_connect_unknown_exchange_id_raises():
    connector = CCXTConnector("ccxt1", "not_a_real_exchange_xyz", AssetClass.CRYPTO)
    with pytest.raises(ConnectorError):
        await connector.connect({})


@pytest.mark.asyncio
async def test_place_market_order_fills_and_opens_position():
    connector, exchange = make_connector()
    await connector.connect({})
    order = Order(asset="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1.0)
    filled = await connector.place_order(order)

    assert filled.status == OrderStatus.FILLED
    assert filled.metadata["fill_price"] == pytest.approx(100.0)
    assert filled.metadata["fee"] == pytest.approx(1.0)
    assert exchange.create_order_calls[0][:4] == ("BTC/USDT", "market", "buy", 1.0)

    position = await connector.get_position("BTC/USDT")
    assert position.quantity == pytest.approx(1.0)
    assert position.entry_price == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_place_order_error_translated_to_connector_error():
    exchange = FakeExchange()

    async def failing_create_order(*args, **kwargs):
        raise RuntimeError("insufficient balance")

    exchange.create_order = failing_create_order
    connector, _ = make_connector(exchange)
    await connector.connect({})

    with pytest.raises(ConnectorError, match="insufficient balance"):
        await connector.place_order(
            Order(asset="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1.0)
        )


@pytest.mark.asyncio
async def test_place_order_not_connected_raises():
    connector, _ = make_connector()
    with pytest.raises(ConnectorError):
        await connector.place_order(
            Order(asset="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1.0)
        )


@pytest.mark.asyncio
async def test_cancel_order_marks_cancelled():
    connector, exchange = make_connector()
    await connector.connect({})
    order = await connector.place_order(
        Order(asset="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=1.0, limit_price=90.0)
    )
    await connector.cancel_order(order.venue_order_id)
    assert exchange.cancel_order_calls == [(order.venue_order_id, "BTC/USDT")]
    status = await connector.get_order_status(order.venue_order_id)
    assert status.status == OrderStatus.CANCELLED


@pytest.mark.asyncio
async def test_get_order_status_unknown_raises():
    connector, _ = make_connector()
    await connector.connect({})
    with pytest.raises(ConnectorError):
        await connector.get_order_status("nonexistent")


@pytest.mark.asyncio
async def test_modify_order_without_edit_support_cancels_and_replaces():
    connector, exchange = make_connector()  # FakeExchange has editOrder=False by default
    await connector.connect({})
    order = await connector.place_order(
        Order(asset="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=1.0, limit_price=90.0)
    )
    original_id = order.venue_order_id

    modified = await connector.modify_order(original_id, quantity=2.0, limit_price=95.0)

    assert modified.venue_order_id != original_id
    assert exchange.cancel_order_calls == [(original_id, "BTC/USDT")]
    assert exchange.create_order_calls[-1][:4] == ("BTC/USDT", "limit", "buy", 2.0)


@pytest.mark.asyncio
async def test_modify_order_with_edit_support_calls_edit_order():
    exchange = FakeExchange()
    exchange.has["editOrder"] = True
    connector, _ = make_connector(exchange)
    await connector.connect({})
    order = await connector.place_order(
        Order(asset="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=1.0, limit_price=90.0)
    )
    original_id = order.venue_order_id  # capture before modify_order mutates `order` in place
    modified = await connector.modify_order(original_id, quantity=3.0)
    assert modified.quantity == 3.0
    assert modified.venue_order_id != original_id  # fake edit_order always returns a new id


@pytest.mark.asyncio
async def test_modify_unknown_order_raises():
    connector, _ = make_connector()
    await connector.connect({})
    with pytest.raises(ConnectorError):
        await connector.modify_order("nonexistent", quantity=1.0)


@pytest.mark.asyncio
async def test_get_live_quote_uses_bid_ask():
    connector, _ = make_connector()
    await connector.connect({})
    quote = await connector.get_live_quote("BTC/USDT")
    assert quote.bid == pytest.approx(99.5)
    assert quote.ask == pytest.approx(100.5)


@pytest.mark.asyncio
async def test_get_live_quote_falls_back_to_last_when_no_bid_ask():
    exchange = FakeExchange()
    exchange._ticker = {"bid": None, "ask": None, "last": 42.0, "timestamp": None}
    connector, _ = make_connector(exchange)
    await connector.connect({})
    quote = await connector.get_live_quote("BTC/USDT")
    assert quote.bid == quote.ask == pytest.approx(42.0)


@pytest.mark.asyncio
async def test_get_live_quote_raises_with_no_price_data_at_all():
    exchange = FakeExchange()
    exchange._ticker = {"bid": None, "ask": None, "last": None}
    connector, _ = make_connector(exchange)
    await connector.connect({})
    with pytest.raises(ConnectorError):
        await connector.get_live_quote("BTC/USDT")


@pytest.mark.asyncio
async def test_get_historical_bars_respects_until_boundary():
    exchange = FakeExchange()
    exchange._ohlcv = [
        [1_700_000_000_000 + i * 60_000, 100 + i, 101 + i, 99 + i, 100 + i, 10.0] for i in range(10)
    ]
    connector, _ = make_connector(exchange)
    await connector.connect({})

    from datetime import datetime, timezone

    start = datetime.fromtimestamp(1_700_000_000_000 / 1000, tz=timezone.utc)
    end = datetime.fromtimestamp((1_700_000_000_000 + 5 * 60_000) / 1000, tz=timezone.utc)
    bars = await connector.get_historical_bars("BTC/USDT", Timeframe.M1, start, end)
    assert len(bars) == 5


@pytest.mark.asyncio
async def test_subscribe_live_data_yields_only_new_bars(monkeypatch):
    # `engine.connectors.ccxt_connector.asyncio` is the same module object as
    # the top-level `asyncio` imported here — capture the real sleep first,
    # or the replacement lambda ends up calling a patched version of itself.
    real_sleep = asyncio.sleep
    monkeypatch.setattr("engine.connectors.ccxt_connector.asyncio.sleep", lambda *_: real_sleep(0))

    exchange = FakeExchange()
    exchange._ohlcv = [[1_700_000_000_000, 100, 101, 99, 100, 10.0]]
    connector, _ = make_connector(exchange)
    await connector.connect({})

    gen = connector.subscribe_live_data(["BTC/USDT"], Timeframe.M1)
    first = await gen.__anext__()
    assert first.close == 100.0

    # A second poll with no new candle should not yield again until the
    # underlying data actually advances.
    exchange._ohlcv = [[1_700_000_060_000, 101, 102, 100, 101, 12.0]]
    second = await gen.__anext__()
    assert second.close == 101.0
    await gen.aclose()


@pytest.mark.asyncio
async def test_subscribe_live_data_rejects_multi_symbol():
    connector, _ = make_connector()
    with pytest.raises(ValueError):
        async for _ in connector.subscribe_live_data(["BTC/USDT", "ETH/USDT"], Timeframe.M1):
            pass


@pytest.mark.asyncio
async def test_get_account_balance_reads_quote_currency():
    connector, _ = make_connector(quote_currency="USDT")
    await connector.connect({})
    assert await connector.get_account_balance() == pytest.approx(10_000.0)


@pytest.mark.asyncio
async def test_get_account_balance_missing_currency_is_zero():
    connector, _ = make_connector(quote_currency="EUR")
    await connector.connect({})
    assert await connector.get_account_balance() == 0.0


@pytest.mark.asyncio
async def test_get_fee_schedule():
    connector, _ = make_connector()
    await connector.connect({})
    assert await connector.get_fee_schedule() == {"maker": 0.001, "taker": 0.0015}


@pytest.mark.asyncio
async def test_get_supported_assets_reads_symbols():
    connector, _ = make_connector()
    await connector.connect({})
    assert connector.get_supported_assets() == ["BTC/USDT", "ETH/USDT"]


@pytest.mark.asyncio
async def test_get_capabilities_reflects_exchange_has():
    exchange = FakeExchange()
    exchange.has["createStopOrder"] = True
    connector, _ = make_connector(exchange)
    await connector.connect({})
    caps = connector.get_capabilities()
    assert caps.supports_short is False
    assert caps.supports_stop is True
    assert caps.supports_websocket is False


def test_map_order_type_rejects_unsupported():
    bad_order = Order(asset="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=1.0, limit_price=1.0)
    bad_order.order_type = "not_a_real_type"
    with pytest.raises(ValueError):
        CCXTConnector._map_order_type(bad_order)
