"""Lightweight test helpers distributed to strategy authors as part of the SDK
(DOC 3 §10)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from common.enums import Timeframe
from .models.bar import Bar
from .models.strategy_config import StrategyConfig
from .strategy_base import StrategyBase


def MockBar(
    asset: str = "BTC/USD",
    timeframe: Timeframe = Timeframe.H1,
    timestamp: datetime | None = None,
    open: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
    volume: float = 10.0,
) -> Bar:
    return Bar(
        asset=asset,
        timeframe=timeframe,
        timestamp=timestamp or datetime.now(timezone.utc),
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


class StrategyTestRunner:
    """Drives a StrategyBase instance through a sequence of bars outside the
    Engine, for strategy-author unit tests."""

    def __init__(self, strategy: StrategyBase, config: StrategyConfig) -> None:
        self.strategy = strategy
        self.config = config
        self.strategy.initialize(config)

    def run(self, bars: list[Bar]) -> list[list]:
        """Feeds bars in order, returns the list of Signal lists produced per bar."""
        results = []
        for bar in bars:
            results.append(self.strategy.on_bar(bar))
        return results

    def make_series(
        self,
        closes: list[float],
        asset: str = "BTC/USD",
        timeframe: Timeframe = Timeframe.H1,
        start: datetime | None = None,
        interval: timedelta = timedelta(hours=1),
    ) -> list[Bar]:
        """Builds a simple bar series from a list of close prices (open=prev close,
        high/low padded by 0.1%, volume fixed at 1.0) — convenient for quick tests."""
        start = start or datetime.now(timezone.utc)
        bars = []
        prev_close = closes[0]
        for i, close in enumerate(closes):
            open_ = prev_close
            high = max(open_, close) * 1.001
            low = min(open_, close) * 0.999
            bars.append(
                Bar(
                    asset=asset,
                    timeframe=timeframe,
                    timestamp=start + interval * i,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=1.0,
                )
            )
            prev_close = close
        return bars

    def validate_schema(self) -> None:
        """Confirms get_parameters_schema() returns well-formed definitions
        (raises via ParameterDefinition.__post_init__ if malformed)."""
        for definition in self.strategy.get_parameters_schema():
            assert definition.name, "ParameterDefinition.name must be non-empty"

    def validate_state_roundtrip(self) -> None:
        """Confirms get_state()/set_state() round-trip through JSON, the
        actual persistence boundary (DOC 3 §7)."""
        state = self.strategy.get_state()
        serialized = json.dumps(state)
        restored: dict[str, Any] = json.loads(serialized)
        self.strategy.set_state(restored)
