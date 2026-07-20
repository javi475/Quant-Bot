"""Order placement, fill processing, and flatten operations, wrapping one or
more ConnectorBase instances (DOC 2 §2.4, §5). Distinguishes an opening fill
from a closing fill purely by whether a trade is already open for that
(strategy_id, asset) pair — consistent with the Engine's no-pyramiding,
single-position-per-asset model (same rule engine.backtest.runner uses).
"""

from __future__ import annotations

from datetime import datetime, timezone

from common.enums import OrderSide, OrderStatus, OrderType
from engine.connectors.base import ConnectorBase
from engine.core.repository import TradeRepository
from engine.models.order import Fill, Order


class ExecutionManager:
    def __init__(self, connectors: dict[str, ConnectorBase], repository: TradeRepository) -> None:
        self.connectors = connectors
        self.repository = repository

    async def place_order(self, connector_id: str, order: Order, strategy_id: str) -> Fill | None:
        connector = self.connectors[connector_id]
        filled_order = await connector.place_order(order)
        if filled_order.status != OrderStatus.FILLED:
            return None
        fill = self._order_to_fill(filled_order)
        await self._record_fill(strategy_id, connector_id, fill)
        return fill

    async def cancel_order(self, connector_id: str, order_id: str) -> None:
        await self.connectors[connector_id].cancel_order(order_id)

    async def process_pending_orders(
        self, connector_id: str, strategy_id_by_asset: dict[str, str]
    ) -> list[Fill]:
        connector = self.connectors[connector_id]
        poll = getattr(connector, "process_pending_orders", None)
        if poll is None:
            return []  # real venues push fills asynchronously; nothing to poll here

        fills = await poll()
        for fill in fills:
            strategy_id = strategy_id_by_asset.get(fill.asset, "")
            await self._record_fill(strategy_id, connector_id, fill)
        return fills

    async def flatten_all(
        self, connector_id: str, strategy_id_by_asset: dict[str, str] | None = None
    ) -> list[Fill]:
        connector = self.connectors[connector_id]
        strategy_id_by_asset = strategy_id_by_asset or {}

        positions = await connector.get_all_positions()
        fills: list[Fill] = []
        for position in positions:
            side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
            order = Order(
                asset=position.asset, side=side, order_type=OrderType.MARKET, quantity=abs(position.quantity)
            )
            filled_order = await connector.place_order(order)
            fill = self._order_to_fill(filled_order)
            strategy_id = strategy_id_by_asset.get(position.asset, "")
            await self._record_fill(strategy_id, connector_id, fill)
            fills.append(fill)
        return fills

    @staticmethod
    def _order_to_fill(order: Order) -> Fill:
        return Fill(
            order_id=order.client_order_id,
            venue_order_id=order.venue_order_id,
            asset=order.asset,
            side=order.side,
            quantity=order.quantity,
            price=order.metadata["fill_price"],
            fee=order.metadata["fee"],
            timestamp=datetime.now(timezone.utc),
        )

    async def _record_fill(self, strategy_id: str, connector_id: str, fill: Fill) -> None:
        open_trades = await self.repository.get_open_trades(strategy_id)
        matching = next((t for t in open_trades if t.asset == fill.asset), None)

        if matching is not None:
            await self.repository.close_trade(matching.trade_id, fill.timestamp, fill.price, fill.fee)
        else:
            side = "long" if fill.side == OrderSide.BUY else "short"
            await self.repository.open_trade(
                strategy_id, connector_id, fill.asset, side, fill.quantity, fill.timestamp, fill.price, fill.fee
            )
