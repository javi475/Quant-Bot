"""Live quote contract returned by ConnectorBase.get_live_quote (DOC 2 §4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Quote:
    asset: str
    bid: float
    ask: float
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.bid <= 0 or self.ask <= 0:
            raise ValueError(f"Quote bid/ask must be positive: bid={self.bid}, ask={self.ask}")
        if self.ask < self.bid:
            raise ValueError(f"Quote ask {self.ask} < bid {self.bid}")

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2
