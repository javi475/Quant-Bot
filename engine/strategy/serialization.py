"""JSON encode/decode helpers for the objects that cross the strategy subprocess
IPC boundary (Bar/Tick/Signal/FillNotification/StrategyConfig/ParameterDefinition).
Kept explicit (rather than a generic asdict()) so enums and datetimes round-trip
to the correct types on both sides of the pipe."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from common.enums import AssetClass, Direction, OrderStatus, ParameterType, Timeframe
from sdk.ate_smp.models.bar import Bar, Tick
from sdk.ate_smp.models.signal import FillNotification, Signal
from sdk.ate_smp.models.strategy_config import ParameterDefinition, RegimeFilter, StrategyConfig


def encode_bar(bar: Bar) -> dict[str, Any]:
    return {
        "asset": bar.asset,
        "timeframe": bar.timeframe.value,
        "timestamp": bar.timestamp.isoformat(),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }


def decode_bar(data: dict[str, Any]) -> Bar:
    return Bar(
        asset=data["asset"],
        timeframe=Timeframe(data["timeframe"]),
        timestamp=datetime.fromisoformat(data["timestamp"]),
        open=data["open"],
        high=data["high"],
        low=data["low"],
        close=data["close"],
        volume=data["volume"],
    )


def encode_tick(tick: Tick) -> dict[str, Any]:
    return {
        "asset": tick.asset,
        "timestamp": tick.timestamp.isoformat(),
        "price": tick.price,
        "size": tick.size,
    }


def decode_tick(data: dict[str, Any]) -> Tick:
    return Tick(
        asset=data["asset"],
        timestamp=datetime.fromisoformat(data["timestamp"]),
        price=data["price"],
        size=data["size"],
    )


def encode_signal(signal: Signal) -> dict[str, Any]:
    return {
        "timestamp": signal.timestamp.isoformat(),
        "asset": signal.asset,
        "direction": signal.direction.value,
        "strength": signal.strength,
        "limit_price": signal.limit_price,
        "metadata": signal.metadata,
    }


def decode_signal(data: dict[str, Any]) -> Signal:
    return Signal(
        timestamp=datetime.fromisoformat(data["timestamp"]),
        asset=data["asset"],
        direction=Direction(data["direction"]),
        strength=data["strength"],
        limit_price=data.get("limit_price"),
        metadata=data.get("metadata", {}),
    )


def encode_fill_notification(fill: FillNotification) -> dict[str, Any]:
    return {
        "order_id": fill.order_id,
        "asset": fill.asset,
        "quantity": fill.quantity,
        "price": fill.price,
        "status": fill.status.value,
        "timestamp": fill.timestamp.isoformat(),
        "metadata": fill.metadata,
    }


def decode_fill_notification(data: dict[str, Any]) -> FillNotification:
    return FillNotification(
        order_id=data["order_id"],
        asset=data["asset"],
        quantity=data["quantity"],
        price=data["price"],
        status=OrderStatus(data["status"]),
        timestamp=datetime.fromisoformat(data["timestamp"]),
        metadata=data.get("metadata", {}),
    )


def encode_config(config: StrategyConfig) -> dict[str, Any]:
    return {
        "asset_class": config.asset_class.value,
        "symbols": list(config.symbols),
        "timeframes": [tf.value for tf in config.timeframes],
        "parameters": config.parameters,
        "regime_filter": (
            {
                "allowed_volatility": list(config.regime_filter.allowed_volatility),
                "allowed_trend": list(config.regime_filter.allowed_trend),
                "atr_percentile_window": config.regime_filter.atr_percentile_window,
                "sma_period": config.regime_filter.sma_period,
            }
            if config.regime_filter
            else None
        ),
        "max_position_holding_hours": config.max_position_holding_hours,
        "connector_id": config.connector_id,
        "capital_allocation": config.capital_allocation,
    }


def decode_config(data: dict[str, Any]) -> StrategyConfig:
    regime_data = data.get("regime_filter")
    regime_filter = (
        RegimeFilter(
            allowed_volatility=tuple(regime_data["allowed_volatility"]),
            allowed_trend=tuple(regime_data["allowed_trend"]),
            atr_percentile_window=regime_data["atr_percentile_window"],
            sma_period=regime_data["sma_period"],
        )
        if regime_data
        else None
    )
    return StrategyConfig(
        asset_class=AssetClass(data["asset_class"]),
        symbols=tuple(data["symbols"]),
        timeframes=tuple(Timeframe(tf) for tf in data["timeframes"]),
        parameters=data.get("parameters", {}),
        regime_filter=regime_filter,
        max_position_holding_hours=data.get("max_position_holding_hours"),
        connector_id=data.get("connector_id", ""),
        capital_allocation=data.get("capital_allocation", 0.30),
    )


def encode_parameter_definition(definition: ParameterDefinition) -> dict[str, Any]:
    return {
        "name": definition.name,
        "type": definition.type.value,
        "default": definition.default,
        "min": definition.min,
        "max": definition.max,
        "choices": list(definition.choices) if definition.choices else None,
        "description": definition.description,
        "unit": definition.unit,
        "group": definition.group,
        "required": definition.required,
        "sensitive": definition.sensitive,
    }


def decode_parameter_definition(data: dict[str, Any]) -> ParameterDefinition:
    return ParameterDefinition(
        name=data["name"],
        type=ParameterType(data["type"]),
        default=data["default"],
        min=data.get("min"),
        max=data.get("max"),
        choices=tuple(data["choices"]) if data.get("choices") else None,
        description=data.get("description", ""),
        unit=data.get("unit", ""),
        group=data.get("group", "general"),
        required=data.get("required", True),
        sensitive=data.get("sensitive", False),
    )
