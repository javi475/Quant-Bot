from datetime import datetime, timedelta, timezone

import pytest

from engine.risk.risk_config import RiskConfig
from engine.risk.safe_mode import SafeModeManager, SafeModePhase

T0 = datetime(2026, 7, 19, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def manager():
    return SafeModeManager(RiskConfig())


def test_inactive_by_default(manager):
    assert not manager.is_active
    assert manager.size_multiplier(T0) == 1.0
    assert manager.entries_allowed(T0)


def test_daily_loss_breaker_allows_reduced_entries(manager):
    manager.activate("daily_loss_breaker", halt_new_entries=False, requires_manual_restart=False, now=T0)
    assert manager.phase == SafeModePhase.ENTRY_BLOCK
    assert manager.entries_allowed(T0)
    assert manager.size_multiplier(T0) == pytest.approx(0.50)


def test_drawdown_ceiling_halts_entries(manager):
    manager.activate("drawdown_ceiling", halt_new_entries=True, requires_manual_restart=True, now=T0)
    assert not manager.entries_allowed(T0)
    assert manager.size_multiplier(T0) == 0.0


def test_daily_loss_breaker_auto_advances_to_recovery_after_block(manager):
    manager.activate("daily_loss_breaker", halt_new_entries=False, requires_manual_restart=False, now=T0)
    after_block = T0 + timedelta(hours=49)
    assert manager.size_multiplier(after_block) == pytest.approx(0.50)  # first 2 recovery days
    assert manager.phase == SafeModePhase.RECOVERY


def test_manual_restart_required_for_drawdown_ceiling(manager):
    manager.activate("drawdown_ceiling", halt_new_entries=True, requires_manual_restart=True, now=T0)
    after_block = T0 + timedelta(hours=49)
    # still blocked: 48h elapsed but no manual restart yet
    assert manager.size_multiplier(after_block) == 0.0
    assert manager.phase == SafeModePhase.ENTRY_BLOCK


def test_manual_restart_transitions_to_recovery(manager):
    manager.activate("drawdown_ceiling", halt_new_entries=True, requires_manual_restart=True, now=T0)
    restart_time = T0 + timedelta(hours=60)
    manager.manual_restart(restart_time)
    assert manager.phase == SafeModePhase.RECOVERY
    assert manager.size_multiplier(restart_time) == pytest.approx(0.50)


def test_manual_restart_raises_outside_entry_block(manager):
    with pytest.raises(ValueError):
        manager.manual_restart(T0)


def test_recovery_graduated_schedule(manager):
    manager.activate("daily_loss_breaker", halt_new_entries=False, requires_manual_restart=False, now=T0)
    block_end = T0 + timedelta(hours=48)

    day1 = block_end + timedelta(days=1)
    assert manager.size_multiplier(day1) == pytest.approx(0.50)

    day3 = block_end + timedelta(days=3)
    assert manager.size_multiplier(day3) == pytest.approx(0.75)

    day5 = block_end + timedelta(days=5)
    assert manager.size_multiplier(day5) == pytest.approx(1.0)


def test_fully_recovers_to_inactive_after_recovery_window(manager):
    manager.activate("daily_loss_breaker", halt_new_entries=False, requires_manual_restart=False, now=T0)
    fully_recovered = T0 + timedelta(hours=48) + timedelta(days=8)
    assert manager.size_multiplier(fully_recovered) == 1.0
    assert manager.phase == SafeModePhase.INACTIVE
    assert not manager.is_active


def test_retrigger_during_recovery_escalates_to_full_halt(manager):
    manager.activate("daily_loss_breaker", halt_new_entries=False, requires_manual_restart=False, now=T0)
    recovery_time = T0 + timedelta(hours=48) + timedelta(days=1)
    manager.size_multiplier(recovery_time)  # ensure phase advances to RECOVERY
    assert manager.phase == SafeModePhase.RECOVERY

    manager.activate("daily_loss_breaker", halt_new_entries=False, requires_manual_restart=False, now=recovery_time)
    assert manager.phase == SafeModePhase.ENTRY_BLOCK
    assert manager.halt_new_entries is True
    assert manager.requires_manual_restart is True
    assert manager.size_multiplier(recovery_time) == 0.0
