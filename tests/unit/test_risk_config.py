import pytest

from engine.risk.risk_config import RiskConfig, RiskConfigError


def test_default_config_is_valid():
    RiskConfig().validate()


@pytest.mark.parametrize(
    "field,value",
    [
        ("kelly_multiplier", 0.05),
        ("kelly_multiplier", 0.60),
        ("max_risk_per_trade", 0.001),
        ("max_risk_per_trade", 0.05),
        ("daily_loss_breaker", -0.10),
        ("daily_loss_breaker", 0.0),
        ("max_drawdown", 0.05),
        ("max_concurrent_positions", 0),
        ("max_concurrent_positions", 20),
        ("max_gross_exposure", 0.10),
        ("correlation_cap", 0.99),
        ("heartbeat_timeout_seconds", 30),
        ("post_breaker_size_mult", 0.90),
        ("max_leverage", 3.0),
        ("min_portfolio_value", 50.0),
    ],
)
def test_out_of_range_values_rejected(field, value):
    config = RiskConfig(**{field: value})
    with pytest.raises(RiskConfigError):
        config.validate()


def test_min_allocation_must_not_exceed_max_allocation():
    config = RiskConfig(per_strategy_min_allocation=0.50, per_strategy_max_allocation=0.40)
    with pytest.raises(RiskConfigError):
        config.validate()


def test_drawdown_alert_ordering_enforced():
    config = RiskConfig(drawdown_alert_1=0.12, drawdown_alert_2=0.10, drawdown_alert_3=0.08)
    with pytest.raises(RiskConfigError):
        config.validate()


def test_recovery_phase_ordering_enforced():
    config = RiskConfig(recovery_phase_1_days=7, recovery_phase_2_days=4, recovery_phase_3_days=2)
    with pytest.raises(RiskConfigError):
        config.validate()


def test_from_dict_ignores_unknown_keys_and_validates():
    config = RiskConfig.from_dict({"kelly_multiplier": 0.30, "not_a_field": 123})
    assert config.kelly_multiplier == 0.30


def test_from_dict_raises_on_invalid_values():
    with pytest.raises(RiskConfigError):
        RiskConfig.from_dict({"max_leverage": 10.0})
