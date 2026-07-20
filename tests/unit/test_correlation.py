import pytest

from engine.risk.correlation import CorrelationManager
from engine.risk.risk_config import RiskConfig


def make_manager():
    return CorrelationManager(RiskConfig())


def test_identical_series_fully_correlated_and_exceeds_cap():
    manager = make_manager()
    returns = [0.01, -0.02, 0.03, -0.01, 0.02, 0.01, -0.03]
    result = manager.check_correlation(returns, {"ETH/USD": returns})
    assert result.exceeded
    assert result.max_correlation == pytest.approx(1.0, abs=1e-9)
    assert result.correlated_symbol == "ETH/USD"


def test_inverse_series_also_exceeds_cap_via_abs_value():
    manager = make_manager()
    returns_a = [0.01, -0.02, 0.03, -0.01, 0.02, 0.01, -0.03]
    returns_b = [-x for x in returns_a]
    result = manager.check_correlation(returns_a, {"ETH/USD": returns_b})
    assert result.exceeded
    assert result.max_correlation == pytest.approx(-1.0, abs=1e-9)


def test_uncorrelated_series_does_not_exceed_cap():
    manager = make_manager()
    returns_a = [0.01, -0.02, 0.03, -0.01, 0.02, 0.01, -0.03, 0.015, -0.005, 0.02]
    returns_b = [0.02, 0.01, -0.01, 0.03, -0.02, -0.015, 0.01, -0.02, 0.005, 0.0]
    result = manager.check_correlation(returns_a, {"ETH/USD": returns_b})
    assert not result.exceeded


def test_insufficient_data_pair_is_skipped_not_blocked():
    manager = make_manager()
    result = manager.check_correlation([0.01], {"ETH/USD": [0.02]})
    assert not result.exceeded
    assert result.correlated_symbol is None


def test_zero_variance_series_does_not_crash():
    manager = make_manager()
    flat = [0.0, 0.0, 0.0, 0.0]
    result = manager.check_correlation([0.01, 0.02, -0.01, 0.03], {"ETH/USD": flat})
    assert not result.exceeded


def test_picks_the_most_correlated_of_multiple_positions():
    manager = make_manager()
    new_returns = [0.01, -0.02, 0.03, -0.01, 0.02, 0.01, -0.03]
    low_corr = [0.02, 0.01, -0.01, 0.03, -0.02, -0.015, 0.01]
    high_corr = new_returns  # identical -> correlation 1.0
    result = manager.check_correlation(
        new_returns, {"LOW/USD": low_corr, "HIGH/USD": high_corr}
    )
    assert result.correlated_symbol == "HIGH/USD"
    assert result.exceeded
