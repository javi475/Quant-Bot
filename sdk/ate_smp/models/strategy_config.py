"""Strategy configuration & parameter schema contracts (DOC 3 §1, §4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from common.enums import AssetClass, ParameterType, Timeframe

DEFAULT_CAPITAL_ALLOCATION = 0.30


@dataclass(frozen=True)
class RegimeFilter:
    """Restricts a strategy to specific market regimes (DOC 3 §1)."""

    allowed_volatility: tuple[str, ...] = ("low", "medium", "high")
    allowed_trend: tuple[str, ...] = ("bull", "bear", "sideways")
    atr_percentile_window: int = 90
    sma_period: int = 200


@dataclass(frozen=True)
class ParameterDefinition:
    """One entry in Strategy.get_parameters_schema() (DOC 3 §4)."""

    name: str
    type: ParameterType
    default: Any
    min: Optional[float] = None
    max: Optional[float] = None
    choices: Optional[tuple[Any, ...]] = None
    description: str = ""
    unit: str = ""
    group: str = "general"
    required: bool = True
    sensitive: bool = False

    def __post_init__(self) -> None:
        if self.type == ParameterType.ENUM and not self.choices:
            raise ValueError(f"ParameterDefinition '{self.name}' of type ENUM requires choices")


@dataclass(frozen=True)
class StrategyConfig:
    asset_class: AssetClass
    symbols: tuple[str, ...]
    timeframes: tuple[Timeframe, ...]
    parameters: dict[str, Any] = field(default_factory=dict)
    regime_filter: Optional[RegimeFilter] = None
    max_position_holding_hours: Optional[float] = None
    connector_id: str = ""
    capital_allocation: float = DEFAULT_CAPITAL_ALLOCATION

    def __post_init__(self) -> None:
        if not self.symbols:
            raise ValueError("StrategyConfig requires at least one symbol")
        if not self.timeframes:
            raise ValueError("StrategyConfig requires at least one timeframe")
        if not (0.0 < self.capital_allocation <= 1.0):
            raise ValueError(
                f"StrategyConfig capital_allocation {self.capital_allocation} outside (0.0, 1.0]"
            )
