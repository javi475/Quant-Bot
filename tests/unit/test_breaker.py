from datetime import datetime, timedelta, timezone

import pytest

from engine.risk.breaker import BreakerManager
from engine.risk.risk_config import RiskConfig

DAY1 = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)
DAY2 = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def manager():
    return BreakerManager(RiskConfig())


def test_daily_loss_breaker_not_triggered_within_limit(manager):
    result = manager.check_daily_loss(realized_pnl=-1000, unrealized_pnl=0, nav=100_000, now=DAY1)
    assert not result.triggered
    assert result.daily_pnl_pct == pytest.approx(-0.01)


def test_daily_loss_breaker_triggers_at_threshold(manager):
    result = manager.check_daily_loss(realized_pnl=-3000, unrealized_pnl=0, nav=100_000, now=DAY1)
    assert result.triggered
    assert result.newly_triggered


def test_daily_loss_breaker_uses_realized_plus_unrealized(manager):
    result = manager.check_daily_loss(realized_pnl=-2000, unrealized_pnl=-2000, nav=100_000, now=DAY1)
    assert result.triggered  # -4% total


def test_daily_loss_breaker_newly_triggered_only_once_per_day(manager):
    first = manager.check_daily_loss(realized_pnl=-4000, unrealized_pnl=0, nav=100_000, now=DAY1)
    second = manager.check_daily_loss(
        realized_pnl=-5000, unrealized_pnl=0, nav=100_000, now=DAY1 + timedelta(hours=1)
    )
    assert first.newly_triggered
    assert second.triggered and not second.newly_triggered


def test_daily_loss_breaker_resets_on_new_utc_day(manager):
    manager.check_daily_loss(realized_pnl=-4000, unrealized_pnl=0, nav=100_000, now=DAY1)
    result = manager.check_daily_loss(realized_pnl=-4000, unrealized_pnl=0, nav=100_000, now=DAY2)
    assert result.triggered
    assert result.newly_triggered  # fresh trigger on the new day


def test_daily_loss_breaker_zero_nav_is_safe(manager):
    result = manager.check_daily_loss(realized_pnl=-100, unrealized_pnl=0, nav=0, now=DAY1)
    assert result.daily_pnl_pct == 0.0
    assert not result.triggered


def test_drawdown_tracks_peak_equity(manager):
    manager.check_drawdown(100_000)
    result = manager.check_drawdown(105_000)
    assert result.peak_equity == 105_000
    assert result.current_drawdown == 0.0


def test_drawdown_computed_from_peak(manager):
    manager.check_drawdown(100_000)
    result = manager.check_drawdown(90_000)
    assert result.current_drawdown == pytest.approx(0.10)
    assert not result.breached


def test_drawdown_breach_at_max(manager):
    manager.check_drawdown(100_000)
    result = manager.check_drawdown(85_000)
    assert result.breached
    assert result.alert_level == "breach"


def test_drawdown_alert_levels_graduated(manager):
    manager.check_drawdown(100_000)
    info = manager.check_drawdown(92_000)  # 8% dd
    assert info.alert_level == "info"
    warning = manager.check_drawdown(90_000)  # 10% dd
    assert warning.alert_level == "warning"
    serious = manager.check_drawdown(88_000)  # 12% dd
    assert serious.alert_level == "serious"


def test_drawdown_alert_not_repeated_at_same_level(manager):
    manager.check_drawdown(100_000)
    first = manager.check_drawdown(92_000)
    second = manager.check_drawdown(92_500)  # still ~7.5%, same "info" band
    assert first.newly_escalated
    assert not second.newly_escalated


def test_drawdown_alert_re_escalates_after_recovery(manager):
    manager.check_drawdown(100_000)
    manager.check_drawdown(92_000)  # info
    manager.check_drawdown(99_000)  # recovers below alert_1 -> resets episode
    result = manager.check_drawdown(92_000)  # crosses info threshold again
    assert result.newly_escalated
