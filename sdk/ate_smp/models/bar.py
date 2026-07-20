"""Market data types delivered to strategies (DOC 3 §1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from common.enums import Timeframe


@dataclass(frozen=True)
class Bar:
    asset: str
    timeframe: Timeframe
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if self.high < self.low:
            raise ValueError(f"Bar high {self.high} < low {self.low} for {self.asset}")
        if not (self.low <= self.open <= self.high):
            raise ValueError(f"Bar open {self.open} outside [{self.low}, {self.high}]")
        if not (self.low <= self.close <= self.high):
            raise ValueError(f"Bar close {self.close} outside [{self.low}, {self.high}]")
        if self.volume < 0:
            raise ValueError(f"Bar volume {self.volume} is negative")


@dataclass(frozen=True)
class Tick:
    asset: str
    timestamp: datetime
    price: float
    size: float

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError(f"Tick price {self.price} must be positive")
        if self.size < 0:
            raise ValueError(f"Tick size {self.size} is negative")
