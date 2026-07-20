"""Signal contract strategies return from on_bar/on_tick (DOC 3 §1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from common.enums import Direction, OrderStatus


@dataclass(frozen=True)
class Signal:
    timestamp: datetime
    asset: str
    direction: Direction
    strength: float
    limit_price: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (0.0 <= self.strength <= 1.0):
            raise ValueError(f"Signal strength {self.strength} outside [0.0, 1.0]")
        if self.limit_price is not None and self.limit_price <= 0:
            raise ValueError(f"Signal limit_price {self.limit_price} must be positive")


@dataclass(frozen=True)
class FillNotification:
    """Passed to Strategy.on_fill after an order fills or partially fills."""

    order_id: str
    asset: str
    quantity: float
    price: float
    status: OrderStatus
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
