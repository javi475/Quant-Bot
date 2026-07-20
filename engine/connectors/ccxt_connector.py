"""Live crypto connector via ccxt (DOC 2 §4) — Binance, Kraken, Coinbase,
KuCoin, Bybit, and any other ccxt-supported *spot* exchange. Talks to
ccxt's async_support exchange classes.

Position bookkeeping is tracked internally from confirmed fills (see
engine.connectors.position_book), the same way PaperConnector does, rather
than trusting the venue's balance snapshot — a spot balance alone carries no
entry-price/cost-basis context, so it can't answer "what's the unrealized
P&L on this holding" by itself.

NOT exercised against a live exchange this session — no real API
credentials or reliable outbound network access in this dev environment
(same treatment as engine.data.ccxt_downloader). The connector's own
translation/bookkeeping/error-handling logic is fully unit-tested against a
hand-rolled fake exchange object (tests/unit/test_ccxt_connector.py);
verify manually against a testnet before ever pointing it at real capital.

Order type support: MARKET and LIMIT are universal across ccxt exchanges.
STOP/STOP_LIMIT are passed through as a best-effort `stopPrice` param —
ccxt does not fully unify stop-order semantics across venues, so treat
these as exchange-dependent and verify against the specific venue in use.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

from common.enums import AssetClass, OrderSide, OrderStatus, OrderType, Timeframe
from engine.connectors.base import ConnectorBase, ConnectorCapabilities, ConnectorError
from engine.connectors.position_book import apply_position_delta
from engine.models.order import Order
from engine.models.position import Position
from engine.models.quote import Quote
from sdk.ate_smp.models.bar import Bar

DEFAULT_OHLCV_LIMIT = 1000

# Polling interval used by subscribe_live_data() per timeframe granularity —
# ccxt's REST API has no native async streaming; ccxt.pro (websockets) is a
# separate library not adopted here. Polling is a deliberate, documented
# simplification, not an oversight.
_POLL_INTERVAL_SECONDS: dict[Timeframe, float] = {
    Timeframe.M1: 5.0,
    Timeframe.M5: 15.0,
    Timeframe.M15: 30.0,
    Timeframe.M30: 60.0,
    Timeframe.H1: 60.0,
    Timeframe.H4: 300.0,
    Timeframe.D1: 900.0,
    Timeframe.W1: 3600.0,
}

_STATUS_MAP: dict[str, OrderStatus] = {
    "open": OrderStatus.OPEN,
    "closed": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELLED,
    "cancelled": OrderStatus.CANCELLED,
    "rejected": OrderStatus.REJECTED,
    "expired": OrderStatus.CANCELLED,
}


class CCXTConnector(ConnectorBase):
    def __init__(
        self,
        connector_id: str,
        exchange_id: str,
        asset_class: AssetClass = AssetClass.CRYPTO,
        exchange: Optional[Any] = None,
        quote_currency: str = "USDT",
    ) -> None:
        self.connector_id = connector_id
        self.exchange_id = exchange_id
        self.asset_class = asset_class
        self.quote_currency = quote_currency
        # `exchange` is the dependency-injection point tests use to supply a
        # fake ccxt-shaped object; production code leaves it None and lets
        # connect() build the real ccxt.async_support exchange.
        self._exchange = exchange

        self._connected = False
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, Order] = {}

    # ----- Connection lifecycle -----

    async def connect(self, credentials: dict[str, Any]) -> None:
        if self._exchange is None:
            import ccxt.async_support as ccxt_async

            if not hasattr(ccxt_async, self.exchange_id):
                raise ConnectorError(f"unknown ccxt exchange id: {self.exchange_id}")
            exchange_class = getattr(ccxt_async, self.exchange_id)
            self._exchange = exchange_class(
                {
                    "apiKey": credentials.get("api_key"),
                    "secret": credentials.get("api_secret"),
                    "password": credentials.get("passphrase"),  # KuCoin, Coinbase, etc.
                    "enableRateLimit": True,
                }
            )

        try:
            await self._exchange.load_markets()
        except Exception as exc:  # ccxt's exception hierarchy is broad and version-specific
            raise ConnectorError(f"failed to connect to {self.exchange_id}: {exc}") from exc
        self._connected = True

    async def disconnect(self) -> None:
        if self._exchange is not None and hasattr(self._exchange, "close"):
            await self._exchange.close()
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # ----- Market data -----

    async def get_historical_bars(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[Bar]:
        since_ms = int(start.timestamp() * 1000)
        until_ms = int(end.timestamp() * 1000)
        bars: list[Bar] = []
        cursor = since_ms

        while cursor < until_ms:
            candles = await self._exchange.fetch_ohlcv(
                symbol, timeframe=timeframe.value, since=cursor, limit=DEFAULT_OHLCV_LIMIT
            )
            if not candles:
                break
            for ts_ms, o, h, l, c, v in candles:
                if ts_ms >= until_ms:
                    break
                bars.append(
                    Bar(
                        asset=symbol,
                        timeframe=timeframe,
                        timestamp=datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
                        open=o, high=h, low=l, close=c, volume=v,
                    )
                )
            if len(candles) < DEFAULT_OHLCV_LIMIT:
                break
            cursor = candles[-1][0] + 1

        return bars

    async def subscribe_live_data(self, symbols: list[str], timeframe: Timeframe) -> AsyncIterator[Bar]:
        if len(symbols) != 1:
            raise ValueError(
                "CCXTConnector.subscribe_live_data expects exactly one symbol per call "
                "— subscribe once per symbol (this is what SignalScheduler does)"
            )
        symbol = symbols[0]
        poll_interval = _POLL_INTERVAL_SECONDS.get(timeframe, 60.0)
        last_ts_ms: Optional[int] = None

        while True:
            candles = await self._exchange.fetch_ohlcv(symbol, timeframe=timeframe.value, limit=2)
            if candles:
                ts_ms, o, h, l, c, v = candles[-1]
                if last_ts_ms is None or ts_ms > last_ts_ms:
                    last_ts_ms = ts_ms
                    yield Bar(
                        asset=symbol,
                        timeframe=timeframe,
                        timestamp=datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
                        open=o, high=h, low=l, close=c, volume=v,
                    )
            await asyncio.sleep(poll_interval)

    async def get_live_quote(self, symbol: str) -> Quote:
        try:
            ticker = await self._exchange.fetch_ticker(symbol)
        except Exception as exc:
            raise ConnectorError(f"fetch_ticker failed for {symbol}: {exc}") from exc

        bid, ask = ticker.get("bid"), ticker.get("ask")
        if bid is None or ask is None:
            last = ticker.get("last")
            if last is None:
                raise ConnectorError(f"no quote available for {symbol}")
            bid = ask = last

        ts_ms = ticker.get("timestamp")
        timestamp = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc) if ts_ms else datetime.now(timezone.utc)
        return Quote(asset=symbol, bid=float(bid), ask=float(ask), timestamp=timestamp)

    # ----- Orders -----

    @staticmethod
    def _map_order_type(order: Order) -> tuple[str, dict[str, Any]]:
        if order.order_type == OrderType.MARKET:
            return "market", {}
        if order.order_type == OrderType.LIMIT:
            return "limit", {}
        if order.order_type == OrderType.STOP:
            return "stop", {"stopPrice": order.stop_price}
        if order.order_type == OrderType.STOP_LIMIT:
            return "stop_limit", {"stopPrice": order.stop_price}
        raise ValueError(f"unsupported order type: {order.order_type}")

    @staticmethod
    def _map_status(raw_status: Optional[str]) -> OrderStatus:
        return _STATUS_MAP.get(raw_status or "", OrderStatus.PENDING)

    def _apply_fill_from_raw(self, order: Order, raw: dict[str, Any], is_buy: bool) -> None:
        filled = float(raw.get("filled") or 0.0)
        avg_price = raw.get("average") or raw.get("price")
        if filled <= 0 or not avg_price:
            return
        avg_price = float(avg_price)
        order.metadata["fill_price"] = avg_price
        fee = raw.get("fee") or {}
        order.metadata["fee"] = float(fee.get("cost") or 0.0)
        apply_position_delta(self._positions, order.asset, filled if is_buy else -filled, avg_price)

    async def place_order(self, order: Order) -> Order:
        if not self._connected:
            raise ConnectorError("connector not connected")

        ccxt_type, params = self._map_order_type(order)
        side = "buy" if order.side == OrderSide.BUY else "sell"

        try:
            raw = await self._exchange.create_order(
                order.asset, ccxt_type, side, order.quantity, order.limit_price, params
            )
        except Exception as exc:
            raise ConnectorError(f"order placement failed for {order.asset}: {exc}") from exc

        venue_order_id = str(raw["id"])
        order.venue_order_id = venue_order_id
        order.status = self._map_status(raw.get("status"))
        self._apply_fill_from_raw(order, raw, is_buy=side == "buy")
        self._orders[venue_order_id] = order
        return order

    async def cancel_order(self, order_id: str) -> None:
        cached = self._orders.get(order_id)
        symbol = cached.asset if cached else None
        try:
            await self._exchange.cancel_order(order_id, symbol)
        except Exception as exc:
            raise ConnectorError(f"cancel_order failed for {order_id}: {exc}") from exc
        if cached is not None:
            cached.status = OrderStatus.CANCELLED

    async def modify_order(
        self, order_id: str, quantity: Optional[float] = None, limit_price: Optional[float] = None
    ) -> Order:
        order = self._orders.get(order_id)
        if order is None:
            raise ConnectorError(f"unknown order {order_id}")

        supports_edit = bool(getattr(self._exchange, "has", {}).get("editOrder"))
        if not supports_edit:
            # Most exchanges don't support in-place edits: cancel and re-place.
            await self.cancel_order(order_id)
            replacement = Order(
                asset=order.asset,
                side=order.side,
                order_type=order.order_type,
                quantity=quantity if quantity is not None else order.quantity,
                limit_price=limit_price if limit_price is not None else order.limit_price,
                stop_price=order.stop_price,
            )
            return await self.place_order(replacement)

        ccxt_type, _params = self._map_order_type(order)
        side = "buy" if order.side == OrderSide.BUY else "sell"
        new_quantity = quantity if quantity is not None else order.quantity
        new_price = limit_price if limit_price is not None else order.limit_price
        try:
            raw = await self._exchange.edit_order(order_id, order.asset, ccxt_type, side, new_quantity, new_price)
        except Exception as exc:
            raise ConnectorError(f"edit_order failed for {order_id}: {exc}") from exc

        new_id = str(raw["id"])
        order.venue_order_id = new_id
        order.quantity = new_quantity
        order.limit_price = new_price
        order.status = self._map_status(raw.get("status"))
        self._orders.pop(order_id, None)
        self._orders[new_id] = order
        return order

    async def get_order_status(self, order_id: str) -> Order:
        cached = self._orders.get(order_id)
        if cached is None:
            raise ConnectorError(f"unknown order {order_id}")
        try:
            raw = await self._exchange.fetch_order(order_id, cached.asset)
        except Exception as exc:
            raise ConnectorError(f"fetch_order failed for {order_id}: {exc}") from exc

        cached.status = self._map_status(raw.get("status"))
        is_buy = cached.side == OrderSide.BUY
        self._apply_fill_from_raw(cached, raw, is_buy=is_buy)
        return cached

    # ----- Account -----

    async def get_position(self, symbol: str) -> Optional[Position]:
        return self._positions.get(symbol)

    async def get_all_positions(self) -> list[Position]:
        return list(self._positions.values())

    async def get_account_balance(self) -> float:
        try:
            balance = await self._exchange.fetch_balance()
        except Exception as exc:
            raise ConnectorError(f"fetch_balance failed: {exc}") from exc
        free = balance.get("free", {})
        return float(free.get(self.quote_currency, 0.0) or 0.0)

    async def get_fee_schedule(self) -> dict[str, float]:
        fees = getattr(self._exchange, "fees", None) or {}
        trading = fees.get("trading", {})
        return {"maker": float(trading.get("maker", 0.0) or 0.0), "taker": float(trading.get("taker", 0.0) or 0.0)}

    def get_supported_assets(self) -> list[str]:
        symbols = getattr(self._exchange, "symbols", None)
        return list(symbols) if symbols else []

    def get_capabilities(self) -> ConnectorCapabilities:
        has = getattr(self._exchange, "has", None) or {}
        return ConnectorCapabilities(
            supports_short=False,  # spot exchanges only; margin/futures connectors are a future addition
            supports_limit=bool(has.get("createLimitOrder", True)),
            supports_stop=bool(has.get("createStopOrder", False)),
            supports_websocket=False,  # polling-based subscribe_live_data(), not ccxt.pro
            supports_partial_fills=True,
            max_leverage=1.0,
        )
