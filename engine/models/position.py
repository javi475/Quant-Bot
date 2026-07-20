"""Open-position contract (DOC 2 §4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Position:
    asset: str
    quantity: float
    entry_price: float
    current_price: float
    opened_at: datetime
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    strategy_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @property
    def is_flat(self) -> bool:
        return self.quantity == 0

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    def update_price(self, price: float) -> None:
        if price <= 0:
            raise ValueError(f"Position update price {price} must be positive")
        self.current_price = price
        self.unrealized_pnl = (self.current_price - self.entry_price) * self.quantity
