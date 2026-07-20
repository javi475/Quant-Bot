import pytest

from engine.risk.position_sizer import PositionSizer
from engine.risk.risk_config import RiskConfig


@pytest.fixture
def sizer():
    return PositionSizer(RiskConfig())


def test_kelly_formula_matches_spec(sizer):
    # f* = (p*(b+1) - 1) / b = (0.6*3 - 1) / 2 = 0.4
    result = sizer.calculate_size(
        win_probability=0.6,
        win_loss_ratio=2.0,
        signal_strength=1.0,
        portfolio_value=100_000,
        price=100.0,
    )
    assert result.kelly_fraction_full == pytest.approx(0.4)


def test_applied_fraction_capped_at_max_risk_per_trade(sizer):
    # full kelly 0.4 * 0.25 multiplier * 1.0 strength = 0.10, well above the 2% cap
    result = sizer.calculate_size(
        win_probability=0.6,
        win_loss_ratio=2.0,
        signal_strength=1.0,
        portfolio_value=100_000,
        price=100.0,
    )
    assert not result.rejected
    assert result.kelly_fraction_applied == pytest.approx(0.02)
    assert result.position_value == pytest.approx(2_000.0)
    assert result.quantity == pytest.approx(20.0)


def test_applied_fraction_below_cap_when_inputs_modest(sizer):
    # full kelly = (0.55*2 - 1)/1 = 0.10; applied = 0.10*0.25*0.5 = 0.0125 (< 2% cap)
    result = sizer.calculate_size(
        win_probability=0.55,
        win_loss_ratio=1.0,
        signal_strength=0.5,
        portfolio_value=100_000,
        price=50.0,
    )
    assert not result.rejected
    assert result.kelly_fraction_applied == pytest.approx(0.0125)


def test_negative_kelly_rejected(sizer):
    # full kelly = (0.4*2 - 1)/1 = -0.2 -> clamped to 0 -> rejected
    result = sizer.calculate_size(
        win_probability=0.4,
        win_loss_ratio=1.0,
        signal_strength=1.0,
        portfolio_value=100_000,
        price=100.0,
    )
    assert result.rejected
    assert "non-positive" in result.rejection_reason
    assert result.quantity == 0.0


def test_zero_win_loss_ratio_rejected(sizer):
    result = sizer.calculate_size(
        win_probability=0.6,
        win_loss_ratio=0.0,
        signal_strength=1.0,
        portfolio_value=100_000,
        price=100.0,
    )
    assert result.rejected
    assert "zero" in result.rejection_reason


def test_invalid_negative_win_loss_ratio_defaults_to_one(sizer):
    result_default = sizer.calculate_size(
        win_probability=0.6, win_loss_ratio=1.0, signal_strength=1.0,
        portfolio_value=100_000, price=100.0,
    )
    result_negative = sizer.calculate_size(
        win_probability=0.6, win_loss_ratio=-5.0, signal_strength=1.0,
        portfolio_value=100_000, price=100.0,
    )
    assert result_negative.kelly_fraction_full == pytest.approx(result_default.kelly_fraction_full)


def test_win_probability_clamped_to_bounds(sizer):
    over_one = sizer.calculate_size(
        win_probability=1.5, win_loss_ratio=2.0, signal_strength=1.0,
        portfolio_value=100_000, price=100.0,
    )
    at_one = sizer.calculate_size(
        win_probability=0.999, win_loss_ratio=2.0, signal_strength=1.0,
        portfolio_value=100_000, price=100.0,
    )
    assert over_one.kelly_fraction_full == pytest.approx(at_one.kelly_fraction_full)


def test_zero_signal_strength_rejected(sizer):
    result = sizer.calculate_size(
        win_probability=0.6, win_loss_ratio=2.0, signal_strength=0.0,
        portfolio_value=100_000, price=100.0,
    )
    assert result.rejected
    assert "strength" in result.rejection_reason


def test_below_minimum_portfolio_still_sizes_correctly():
    # The $min_portfolio_value business-rule rejection is RiskManager step 12
    # ("minimum_portfolio"), which runs after sizing in the pipeline (DOC 4
    # §9) — PositionSizer itself sizes any positive portfolio value correctly.
    sizer = PositionSizer(RiskConfig())
    result = sizer.calculate_size(
        win_probability=0.6, win_loss_ratio=2.0, signal_strength=1.0,
        portfolio_value=500.0, price=100.0,
    )
    assert not result.rejected
    assert result.kelly_fraction_applied == pytest.approx(0.02)


def test_nonpositive_portfolio_value_raises(sizer):
    with pytest.raises(ValueError):
        sizer.calculate_size(
            win_probability=0.6, win_loss_ratio=2.0, signal_strength=1.0,
            portfolio_value=0.0, price=100.0,
        )


def test_nonpositive_price_raises(sizer):
    with pytest.raises(ValueError):
        sizer.calculate_size(
            win_probability=0.6, win_loss_ratio=2.0, signal_strength=1.0,
            portfolio_value=100_000, price=0.0,
        )


def test_safe_mode_multiplier_scales_down_size(sizer):
    full = sizer.calculate_size(
        win_probability=0.55, win_loss_ratio=1.0, signal_strength=0.5,
        portfolio_value=100_000, price=50.0, safe_mode_multiplier=1.0,
    )
    halved = sizer.calculate_size(
        win_probability=0.55, win_loss_ratio=1.0, signal_strength=0.5,
        portfolio_value=100_000, price=50.0, safe_mode_multiplier=0.5,
    )
    assert halved.kelly_fraction_applied == pytest.approx(full.kelly_fraction_applied * 0.5)


def test_zero_safe_mode_multiplier_rejects():
    sizer = PositionSizer(RiskConfig())
    result = sizer.calculate_size(
        win_probability=0.6, win_loss_ratio=2.0, signal_strength=1.0,
        portfolio_value=100_000, price=100.0, safe_mode_multiplier=0.0,
    )
    assert result.rejected


def test_implied_stop_loss_long(sizer):
    # max_loss = 2% * 100_000 = 2000; price_move = 2000 / quantity(10) = 200
    stop = sizer.calculate_implied_stop_loss(
        entry_price=1000.0, is_long=True, portfolio_value=100_000, quantity=10.0
    )
    assert stop == pytest.approx(800.0)


def test_implied_stop_loss_short(sizer):
    stop = sizer.calculate_implied_stop_loss(
        entry_price=1000.0, is_long=False, portfolio_value=100_000, quantity=10.0
    )
    assert stop == pytest.approx(1200.0)


def test_implied_stop_loss_rejects_nonpositive_inputs(sizer):
    with pytest.raises(ValueError):
        sizer.calculate_implied_stop_loss(entry_price=0, is_long=True, portfolio_value=100_000, quantity=10)
    with pytest.raises(ValueError):
        sizer.calculate_implied_stop_loss(entry_price=100, is_long=True, portfolio_value=100_000, quantity=0)
