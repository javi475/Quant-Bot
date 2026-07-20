"""Order/Fill contracts exchanged between the Engine and ConnectorBase implementations
(DOC 2 §4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from common.enums import OrderSide, OrderStatus, OrderType, TimeInForce


@dataclass
class Order:
    asset: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: TimeInForce = TimeInForce.GTC
    client_order_id: str = ""
    venue_order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError(f"Order quantity {self.quantity} must be positive")
        if self.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and self.limit_price is None:
            raise ValueError(f"Order type {self.order_type} requires limit_price")
        if self.order_type in (OrderType.STOP, OrderType.STOP_LIMIT) and self.stop_price is None:
            raise ValueError(f"Order type {self.order_type} requires stop_price")


@dataclass(frozen=True)
class Fill:
    order_id: str
    venue_order_id: str
    asset: str
    side: OrderSide
    quantity: float
    price: float
    fee: float
    timestamp: datetime
    is_partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError(f"Fill quantity {self.quantity} must be positive")
        if self.price <= 0:
            raise ValueError(f"Fill price {self.price} must be positive")
        if self.fee < 0:
            raise ValueError(f"Fill fee {self.fee} is negative")
