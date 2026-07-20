from datetime import datetime, timezone

import pytest

from common.enums import OrderSide, OrderType
from engine.models.order import Fill, Order
from engine.models.position import Position
from engine.models.quote import Quote

NOW = datetime.now(timezone.utc)


def test_order_requires_positive_quantity():
    with pytest.raises(ValueError):
        Order(asset="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=0)


def test_limit_order_requires_limit_price():
    with pytest.raises(ValueError):
        Order(asset="BTC/USD", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=1)
    Order(
        asset="BTC/USD",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=1,
        limit_price=100,
    )


def test_stop_order_requires_stop_price():
    with pytest.raises(ValueError):
        Order(asset="BTC/USD", side=OrderSide.SELL, order_type=OrderType.STOP, quantity=1)


def test_fill_rejects_invalid_values():
    with pytest.raises(ValueError):
        Fill(
            order_id="o1",
            venue_order_id="v1",
            asset="BTC/USD",
            side=OrderSide.BUY,
            quantity=0,
            price=100,
            fee=0,
            timestamp=NOW,
        )
    with pytest.raises(ValueError):
        Fill(
            order_id="o1",
            venue_order_id="v1",
            asset="BTC/USD",
            side=OrderSide.BUY,
            quantity=1,
            price=100,
            fee=-1,
            timestamp=NOW,
        )


def test_position_update_price_recomputes_unrealized_pnl():
    pos = Position(
        asset="BTC/USD",
        quantity=2,
        entry_price=100,
        current_price=100,
        opened_at=NOW,
    )
    pos.update_price(110)
    assert pos.unrealized_pnl == 20
    assert pos.is_long
    assert not pos.is_flat


def test_quote_rejects_crossed_book():
    Quote(asset="BTC/USD", bid=100, ask=101, timestamp=NOW)
    with pytest.raises(ValueError):
        Quote(asset="BTC/USD", bid=101, ask=100, timestamp=NOW)


def test_quote_mid():
    q = Quote(asset="BTC/USD", bid=100, ask=102, timestamp=NOW)
    assert q.mid == 101
