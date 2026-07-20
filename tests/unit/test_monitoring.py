from datetime import datetime, timezone

from engine.models.position import Position
from engine.risk.monitoring import RiskStateSnapshot, check_max_loss_exit, compute_gross_exposure
from engine.risk.safe_mode import SafeModePhase

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


def make_position(unrealized_pnl: float, quantity: float = 10.0, price: float = 100.0) -> Position:
    pos = Position(
        asset="BTC/USD",
        quantity=quantity,
        entry_price=price,
        current_price=price,
        opened_at=NOW,
    )
    pos.unrealized_pnl = unrealized_pnl
    return pos


def test_max_loss_exit_triggers_at_threshold():
    pos = make_position(unrealized_pnl=-2000.0)
    assert check_max_loss_exit(pos, portfolio_value=100_000, max_risk_per_trade=0.02)


def test_max_loss_exit_not_triggered_below_threshold():
    pos = make_position(unrealized_pnl=-500.0)
    assert not check_max_loss_exit(pos, portfolio_value=100_000, max_risk_per_trade=0.02)


def test_max_loss_exit_ignores_profitable_positions():
    pos = make_position(unrealized_pnl=5000.0)
    assert not check_max_loss_exit(pos, portfolio_value=100_000, max_risk_per_trade=0.02)


def test_max_loss_exit_handles_zero_portfolio():
    pos = make_position(unrealized_pnl=-2000.0)
    assert not check_max_loss_exit(pos, portfolio_value=0, max_risk_per_trade=0.02)


def test_compute_gross_exposure_sums_absolute_market_value():
    positions = [
        make_position(unrealized_pnl=0, quantity=10, price=100),  # 1000
        make_position(unrealized_pnl=0, quantity=-5, price=200),  # -1000 -> abs 1000
    ]
    exposure = compute_gross_exposure(positions, portfolio_value=10_000)
    assert exposure == 0.20


def test_compute_gross_exposure_zero_portfolio_is_safe():
    positions = [make_position(unrealized_pnl=0, quantity=10, price=100)]
    assert compute_gross_exposure(positions, portfolio_value=0) == 0.0


def test_risk_state_snapshot_serializes():
    snapshot = RiskStateSnapshot(
        timestamp=NOW,
        equity=100_000.0,
        daily_pnl_pct=-0.01,
        drawdown_pct=0.05,
        gross_exposure_pct=0.30,
        open_position_count=2,
        safe_mode_active=False,
        safe_mode_phase=SafeModePhase.INACTIVE,
    )
    data = snapshot.to_dict()
    assert data["safe_mode_phase"] == "inactive"
    assert data["open_position_count"] == 2
