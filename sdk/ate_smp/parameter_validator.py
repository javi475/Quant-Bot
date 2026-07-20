"""Validates strategy parameter values against a ParameterDefinition schema
(DOC 3 §4). Used by the backend when a dashboard form is submitted, and by
StrategyTestRunner in tests."""

from __future__ import annotations

from typing import Any

from common.enums import ParameterType
from .models.strategy_config import ParameterDefinition

_NUMERIC_TYPES = (ParameterType.FLOAT, ParameterType.INTEGER)
_LIST_TYPES = (ParameterType.LIST_FLOAT, ParameterType.LIST_STRING)


class ParameterValidationError(ValueError):
    pass


class ParameterValidator:
    """Type-coerces and range-checks a dict of raw parameter values against a
    list of ParameterDefinition. Returns a new dict of coerced values."""

    def __init__(self, schema: list[ParameterDefinition]) -> None:
        self.schema = {p.name: p for p in schema}

    def validate(self, values: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, definition in self.schema.items():
            if name not in values:
                if definition.required and definition.default is None:
                    raise ParameterValidationError(f"Missing required parameter '{name}'")
                result[name] = definition.default
                continue
            result[name] = self._coerce_and_check(definition, values[name])

        unknown = set(values) - set(self.schema)
        if unknown:
            raise ParameterValidationError(f"Unknown parameter(s): {sorted(unknown)}")
        return result

    def _coerce_and_check(self, definition: ParameterDefinition, raw: Any) -> Any:
        name, ptype = definition.name, definition.type

        if ptype == ParameterType.FLOAT:
            value = float(raw)
        elif ptype == ParameterType.INTEGER:
            value = int(raw)
        elif ptype == ParameterType.BOOLEAN:
            value = bool(raw)
        elif ptype == ParameterType.STRING:
            value = str(raw)
        elif ptype == ParameterType.ENUM:
            value = raw
            if definition.choices and value not in definition.choices:
                raise ParameterValidationError(
                    f"Parameter '{name}' value {value!r} not in choices {definition.choices}"
                )
            return value
        elif ptype == ParameterType.LIST_FLOAT:
            value = [float(v) for v in raw]
            return value
        elif ptype == ParameterType.LIST_STRING:
            value = [str(v) for v in raw]
            return value
        else:
            raise ParameterValidationError(f"Unsupported parameter type: {ptype}")

        if ptype in _NUMERIC_TYPES:
            if definition.min is not None and value < definition.min:
                raise ParameterValidationError(
                    f"Parameter '{name}' value {value} below min {definition.min}"
                )
            if definition.max is not None and value > definition.max:
                raise ParameterValidationError(
                    f"Parameter '{name}' value {value} above max {definition.max}"
                )
        return value
