"""Simulated execution venue (DOC 2 §2.4, "Paper" connector for M4). Fills
MARKET orders immediately against a synthetic bid/ask spread; LIMIT/STOP
orders sit pending until `process_pending_orders()` finds them marketable.
Reuses the M3 TransactionCostModel for fees/slippage so paper-trading costs
behave consistently with backtest costs.

Position accounting mirrors engine.backtest.runner's unified signed-quantity
rule: buys are positive delta, sells are negative delta, cash always moves by
`-delta * fill_price - fee`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from common.enums import AssetClass, OrderSide, OrderStatus, OrderType, Timeframe
from engine.backtest.cost_model import TransactionCostModel
from engine.connectors.base import ConnectorBase, ConnectorCapabilities, ConnectorError
from engine.connectors.position_book import apply_position_delta
from engine.connectors.price_feed import ReplayPriceFeed
from engine.models.order import Fill, Order
from engine.models.position import Position
from engine.models.quote import Quote
from sdk.ate_smp.models.bar import Bar


class PaperConnector(ConnectorBase):
    def __init__(
        self,
        connector_id: str,
        asset_class: AssetClass,
        feed: ReplayPriceFeed,
        cost_model: Optional[TransactionCostModel] = None,
        initial_capital: float = 100_000.0,
        spread_bps: float = 5.0,
        max_leverage: float = 1.0,
    ) -> None:
        self.connector_id = connector_id
        self.asset_class = asset_class
        self.feed = feed
        self.cost_model = cost_model or TransactionCostModel()
        self.cash = initial_capital
        self.spread_bps = spread_bps
        self.max_leverage = max_leverage

        self._connected = False
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, Order] = {}
        self._pending_orders: dict[str, Order] = {}
        self._next_order_seq = 0

    # ----- Connection lifecycle -----

    async def connect(self, credentials: dict) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # ----- Market data -----

    async def get_historical_bars(self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime) -> list[Bar]:
        return [b for b in self.feed.get_history(symbol) if start <= b.timestamp <= end]

    async def subscribe_live_data(self, symbols: list[str], timeframe: Timeframe) -> AsyncIterator[Bar]:
        if len(symbols) != 1:
            raise ValueError(
                "PaperConnector.subscribe_live_data expects exactly one symbol per "
                "call — subscribe once per symbol (this is what SignalScheduler does)"
            )
        async for bar in self.feed.stream(symbols[0]):
            yield bar

    async def get_live_quote(self, symbol: str) -> Quote:
        price = self.feed.get_price(symbol)
        if price is None:
            raise ConnectorError(f"no price available for {symbol}")
        half_spread = price * (self.spread_bps / 10_000) / 2
        return Quote(
            asset=symbol,
            bid=price - half_spread,
            ask=price + half_spread,
            timestamp=datetime.now(timezone.utc),
        )

    # ----- Orders -----

    def _next_id(self) -> str:
        self._next_order_seq += 1
        return f"paper_{self.connector_id}_{self._next_order_seq}"

    def _is_marketable(self, order: Order, quote: Quote) -> bool:
        is_buy = order.side == OrderSide.BUY
        if order.order_type == OrderType.LIMIT:
            return order.limit_price >= quote.ask if is_buy else order.limit_price <= quote.bid
        if order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
            return quote.ask >= order.stop_price if is_buy else quote.bid <= order.stop_price
        return False

    async def place_order(self, order: Order) -> Order:
        if not self._connected:
            raise ConnectorError("connector not connected")

        if order.order_type == OrderType.MARKET:
            return await self._fill_now(order, reference_price=None)

        quote = await self.get_live_quote(order.asset)
        if self._is_marketable(order, quote):
            reference_price = order.limit_price if order.order_type == OrderType.LIMIT else None
            return await self._fill_now(order, reference_price=reference_price)

        order.venue_order_id = self._next_id()
        order.status = OrderStatus.OPEN
        self._orders[order.venue_order_id] = order
        self._pending_orders[order.venue_order_id] = order
        return order

    async def _fill_now(self, order: Order, reference_price: Optional[float]) -> Order:
        is_buy = order.side == OrderSide.BUY

        if reference_price is not None:
            fill_price = reference_price  # limit orders fill at their own limit price
        else:
            quote = await self.get_live_quote(order.asset)
            raw_price = quote.ask if is_buy else quote.bid
            fill_price = self.cost_model.apply_slippage(raw_price, is_buy=is_buy)

        notional = order.quantity * fill_price
        fee = self.cost_model.compute_fee(notional, order.quantity)
        delta = order.quantity if is_buy else -order.quantity

        self.cash -= delta * fill_price + fee
        apply_position_delta(self._positions, order.asset, delta, fill_price)

        order.venue_order_id = order.venue_order_id or self._next_id()
        order.status = OrderStatus.FILLED
        order.metadata["fill_price"] = fill_price
        order.metadata["fee"] = fee
        self._orders[order.venue_order_id] = order
        self._pending_orders.pop(order.venue_order_id, None)
        return order

    async def process_pending_orders(self) -> list[Fill]:
        """Called each Engine cycle to check whether any pending LIMIT/STOP
        order has since become marketable."""
        fills: list[Fill] = []
        for order_id in list(self._pending_orders.keys()):
            order = self._pending_orders[order_id]
            quote = await self.get_live_quote(order.asset)
            if not self._is_marketable(order, quote):
                continue

            reference_price = order.limit_price if order.order_type == OrderType.LIMIT else None
            filled_order = await self._fill_now(order, reference_price=reference_price)
            fills.append(
                Fill(
                    order_id=filled_order.client_order_id,
                    venue_order_id=filled_order.venue_order_id,
                    asset=filled_order.asset,
                    side=filled_order.side,
                    quantity=filled_order.quantity,
                    price=filled_order.metadata["fill_price"],
                    fee=filled_order.metadata["fee"],
                    timestamp=datetime.now(timezone.utc),
                )
            )
        return fills

    async def cancel_order(self, order_id: str) -> None:
        pending = self._pending_orders.pop(order_id, None)
        if pending is None:
            raise ConnectorError(f"order {order_id} not found or already filled")
        pending.status = OrderStatus.CANCELLED

    async def modify_order(self, order_id: str, quantity: Optional[float] = None, limit_price: Optional[float] = None) -> Order:
        order = self._pending_orders.get(order_id)
        if order is None:
            raise ConnectorError(f"order {order_id} is not pending")
        if quantity is not None:
            order.quantity = quantity
        if limit_price is not None:
            order.limit_price = limit_price
        return order

    async def get_order_status(self, order_id: str) -> Order:
        order = self._orders.get(order_id)
        if order is None:
            raise ConnectorError(f"unknown order {order_id}")
        return order

    # ----- Account -----

    async def get_position(self, symbol: str) -> Optional[Position]:
        return self._positions.get(symbol)

    async def get_all_positions(self) -> list[Position]:
        return list(self._positions.values())

    async def get_account_balance(self) -> float:
        return self.cash

    async def get_fee_schedule(self) -> dict[str, float]:
        return {"maker": self.cost_model.maker_fee, "taker": self.cost_model.taker_fee}

    def get_supported_assets(self) -> list[str]:
        return self.feed.known_symbols() or ["*"]

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_short=True,
            supports_limit=True,
            supports_stop=True,
            supports_websocket=False,
            supports_partial_fills=False,
            max_leverage=self.max_leverage,
        )
