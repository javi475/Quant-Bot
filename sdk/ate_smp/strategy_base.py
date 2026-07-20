"""Strategy interface contract every pluggable strategy module must implement
(DOC 3 §1). The Engine never imports a strategy directly — it talks to a
StrategyBase subclass only through the subprocess IPC boundary
(engine/strategy/runtime.py)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models.bar import Bar, Tick
from .models.signal import FillNotification, Signal
from .models.strategy_config import ParameterDefinition, StrategyConfig


class StrategyBase(ABC):
    """Base class for all strategies. Only stdlib + numpy/pandas/statsmodels/scipy/ta
    may be imported (enforced by engine.strategy.sandbox.StrategySandbox). A strategy
    must never place orders directly, access the network/filesystem, or read another
    strategy's state — it may only return Signal objects from on_bar/on_tick."""

    def __init__(self) -> None:
        self.config: StrategyConfig | None = None

    # ----- Required -----

    @abstractmethod
    def initialize(self, config: StrategyConfig) -> None:
        """Called once when the strategy is loaded. Store config, precompute
        any warmup state needed before the first on_bar call."""

    @abstractmethod
    def on_bar(self, bar: Bar) -> list[Signal]:
        """Primary signal-generation entry point. Must return within 5 seconds
        (enforced by the sandboxed subprocess runtime) or the strategy is
        killed and restarted from its last persisted state."""

    @abstractmethod
    def on_tick(self, tick: Tick) -> list[Signal]:
        """Optional tick-level entry point. Return [] if the strategy is
        bar-only (the default for most strategies)."""

    @abstractmethod
    def on_fill(self, fill: FillNotification) -> None:
        """Notified after the Engine fills (or partially fills) an order
        this strategy's signal produced."""

    @abstractmethod
    def get_parameters_schema(self) -> list[ParameterDefinition]:
        """Declares the tunable parameters the dashboard auto-generates a
        form from (DOC 3 §4)."""

    @abstractmethod
    def get_win_probability(self) -> float:
        """Estimated probability of a winning trade, used as `p` in the
        Kelly criterion (DOC 4 §1). Must be in [0.0, 1.0]."""

    @abstractmethod
    def get_win_loss_ratio(self) -> float:
        """Average win / average loss ratio, used as `b` in the Kelly
        criterion (DOC 4 §1). Must be > 0."""

    @abstractmethod
    def get_state(self) -> dict[str, Any]:
        """Returns JSON-serializable internal state for persistence
        (DOC 3 §7). Called every 5 minutes and before hot-swap/shutdown."""

    @abstractmethod
    def set_state(self, state: dict[str, Any]) -> None:
        """Restores internal state on strategy restart or hot-swap. Must
        tolerate state produced by an older/newer version of this strategy
        (backward-compatible field access, e.g. state.get(...))."""

    # ----- Optional overrides -----

    def get_capabilities(self) -> dict[str, Any]:
        return {}

    def get_description(self) -> str:
        return ""

    def get_metadata(self) -> dict[str, Any]:
        return {}

    def on_strategy_disabled(self) -> None:
        pass

    def on_strategy_enabled(self) -> None:
        pass

    def on_regime_change(self, old_regime: str, new_regime: str) -> None:
        pass
