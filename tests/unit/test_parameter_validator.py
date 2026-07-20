import pytest

from ate_smp import ParameterDefinition, ParameterType
from ate_smp.parameter_validator import ParameterValidationError, ParameterValidator


def make_schema():
    return [
        ParameterDefinition(name="period", type=ParameterType.INTEGER, default=14, min=1, max=50),
        ParameterDefinition(name="threshold", type=ParameterType.FLOAT, default=0.5, min=0.0, max=1.0),
        ParameterDefinition(name="enabled", type=ParameterType.BOOLEAN, default=True),
        ParameterDefinition(name="label", type=ParameterType.STRING, default="x"),
        ParameterDefinition(
            name="mode", type=ParameterType.ENUM, default="a", choices=("a", "b", "c")
        ),
    ]


def test_applies_defaults_for_missing_values():
    validator = ParameterValidator(make_schema())
    result = validator.validate({})
    assert result == {"period": 14, "threshold": 0.5, "enabled": True, "label": "x", "mode": "a"}


def test_coerces_types():
    validator = ParameterValidator(make_schema())
    result = validator.validate({"period": "20", "threshold": "0.8", "enabled": 1})
    assert result["period"] == 20 and isinstance(result["period"], int)
    assert result["threshold"] == 0.8
    assert result["enabled"] is True


def test_rejects_out_of_range():
    validator = ParameterValidator(make_schema())
    with pytest.raises(ParameterValidationError):
        validator.validate({"period": 100})
    with pytest.raises(ParameterValidationError):
        validator.validate({"threshold": -0.1})


def test_rejects_invalid_enum_choice():
    validator = ParameterValidator(make_schema())
    with pytest.raises(ParameterValidationError):
        validator.validate({"mode": "z"})


def test_rejects_unknown_parameter():
    validator = ParameterValidator(make_schema())
    with pytest.raises(ParameterValidationError):
        validator.validate({"nonexistent": 1})


def test_enum_parameter_requires_choices_at_definition_time():
    with pytest.raises(ValueError):
        ParameterDefinition(name="mode", type=ParameterType.ENUM, default="a", choices=None)


def test_list_float_and_list_string_types():
    schema = [
        ParameterDefinition(name="weights", type=ParameterType.LIST_FLOAT, default=[1.0]),
        ParameterDefinition(name="tags", type=ParameterType.LIST_STRING, default=["x"]),
    ]
    validator = ParameterValidator(schema)
    result = validator.validate({"weights": [1, 2, 3], "tags": ["a", "b"]})
    assert result["weights"] == [1.0, 2.0, 3.0]
    assert result["tags"] == ["a", "b"]
