"""Shared result types for the backtest engine, kept separate from runner.py
to avoid a circular import with metrics.py."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Trade:
    asset: str
    side: str  # "long" | "short"
    quantity: float  # always positive (absolute size)
    entry_time: datetime
    entry_price: float
    entry_fee: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_fee: float = 0.0

    @property
    def is_closed(self) -> bool:
        return self.exit_time is not None

    @property
    def pnl(self) -> Optional[float]:
        if not self.is_closed:
            return None
        direction = 1.0 if self.side == "long" else -1.0
        return (
            direction * (self.exit_price - self.entry_price) * self.quantity
            - self.entry_fee
            - self.exit_fee
        )


@dataclass
class BacktestResult:
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    final_equity: float = 0.0
    metrics: dict = field(default_factory=dict)
