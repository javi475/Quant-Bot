"""Unified venue abstraction (DOC 2 §4). Every broker/exchange/prop-firm/
prediction-market adapter implements this interface; the Engine only ever
talks to a `ConnectorBase`, never to a venue-specific SDK directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, AsyncIterator, Optional

from common.enums import AssetClass, Timeframe
from engine.models.order import Fill, Order
from engine.models.position import Position
from engine.models.quote import Quote
from sdk.ate_smp.models.bar import Bar


class ConnectorError(Exception):
    """Base class for connector-level failures (auth, network, venue rejection)."""


class ConnectorCapabilities:
    def __init__(
        self,
        supports_short: bool = False,
        supports_limit: bool = True,
        supports_stop: bool = True,
        supports_websocket: bool = False,
        supports_partial_fills: bool = False,
        max_leverage: float = 1.0,
        rate_limit_per_minute: Optional[int] = None,
    ) -> None:
        self.supports_short = supports_short
        self.supports_limit = supports_limit
        self.supports_stop = supports_stop
        self.supports_websocket = supports_websocket
        self.supports_partial_fills = supports_partial_fills
        self.max_leverage = max_leverage
        self.rate_limit_per_minute = rate_limit_per_minute

    def to_dict(self) -> dict[str, Any]:
        return {
            "supports_short": self.supports_short,
            "supports_limit": self.supports_limit,
            "supports_stop": self.supports_stop,
            "supports_websocket": self.supports_websocket,
            "supports_partial_fills": self.supports_partial_fills,
            "max_leverage": self.max_leverage,
            "rate_limit_per_minute": self.rate_limit_per_minute,
        }


class ConnectorBase(ABC):
    connector_id: str
    asset_class: AssetClass

    @abstractmethod
    async def connect(self, credentials: dict[str, Any]) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    async def get_historical_bars(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[Bar]: ...

    @abstractmethod
    async def subscribe_live_data(self, symbols: list[str], timeframe: Timeframe) -> AsyncIterator[Bar]:
        """An async generator yielding bars as they become available. Callers
        that need non-blocking polling should consume this from a background
        task feeding their own queue, rather than blocking the main loop."""
        raise NotImplementedError
        yield  # pragma: no cover - makes this a generator function for subclasses

    @abstractmethod
    async def get_live_quote(self, symbol: str) -> Quote: ...

    @abstractmethod
    async def place_order(self, order: Order) -> Order: ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> None: ...

    @abstractmethod
    async def modify_order(
        self, order_id: str, quantity: Optional[float] = None, limit_price: Optional[float] = None
    ) -> Order: ...

    @abstractmethod
    async def get_order_status(self, order_id: str) -> Order: ...

    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[Position]: ...

    @abstractmethod
    async def get_all_positions(self) -> list[Position]: ...

    @abstractmethod
    async def get_account_balance(self) -> float: ...

    @abstractmethod
    async def get_fee_schedule(self) -> dict[str, float]: ...

    @abstractmethod
    def get_supported_assets(self) -> list[str]: ...

    @abstractmethod
    def get_capabilities(self) -> ConnectorCapabilities: ...
