import json
from datetime import datetime, timezone

import pytest

from engine.risk.correlation import CorrelationCheckResult
from engine.risk.position_sizer import PositionSizer
from engine.risk.risk_config import RiskConfig
from engine.risk.risk_manager import CHECK_ORDER, PreTradeContext, RiskManager
from engine.risk.safe_mode import SafeModeManager

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def redirect_decision_audit(tmp_path, monkeypatch):
    target = tmp_path / "decision_audit.jsonl"
    monkeypatch.setattr("engine.risk.risk_manager.decision_audit_path", lambda: str(target))
    return target


def make_manager():
    config = RiskConfig()
    return RiskManager(config, PositionSizer(config), SafeModeManager(config)), config


def base_ctx(**overrides) -> PreTradeContext:
    defaults = dict(
        asset="BTC/USD",
        is_entry=True,
        strategy_enabled=True,
        trading_mode_ok=True,
        now=NOW,
        portfolio_value=100_000.0,
        price=100.0,
        signal_strength=1.0,
        win_probability=0.6,
        win_loss_ratio=2.0,
        current_position_count=0,
        current_gross_exposure=0.0,
        daily_loss_breaker_triggered=False,
        drawdown_breached=False,
        regime_ok=True,
        connector_healthy=True,
        capital_allocation_ok=True,
        correlation_result=None,
        strategy_id="strat_001",
    )
    defaults.update(overrides)
    return PreTradeContext(**defaults)


def test_happy_path_approves_and_sizes(redirect_decision_audit):
    manager, _ = make_manager()
    decision = manager.check_pre_trade(base_ctx())
    assert decision.approved
    assert decision.quantity > 0
    assert [c.name for c in decision.checks] == list(CHECK_ORDER)
    assert all(c.passed for c in decision.checks)


def test_strategy_disabled_rejects_first(redirect_decision_audit):
    manager, _ = make_manager()
    decision = manager.check_pre_trade(base_ctx(strategy_enabled=False))
    assert not decision.approved
    assert [c.name for c in decision.checks] == ["strategy_status"]


def test_daily_loss_breaker_rejects(redirect_decision_audit):
    manager, _ = make_manager()
    decision = manager.check_pre_trade(base_ctx(daily_loss_breaker_triggered=True))
    assert not decision.approved
    assert decision.checks[-1].name == "daily_loss_breaker"


def test_drawdown_ceiling_rejects(redirect_decision_audit):
    manager, _ = make_manager()
    decision = manager.check_pre_trade(base_ctx(drawdown_breached=True))
    assert not decision.approved
    assert decision.checks[-1].name == "drawdown_ceiling"


def test_position_limit_only_checked_on_entry(redirect_decision_audit):
    manager, config = make_manager()
    decision = manager.check_pre_trade(
        base_ctx(current_position_count=config.max_concurrent_positions)
    )
    assert not decision.approved
    assert decision.checks[-1].name == "position_limit"

    exit_decision = manager.check_pre_trade(
        base_ctx(is_entry=False, current_position_count=config.max_concurrent_positions)
    )
    assert exit_decision.approved  # position limit skipped for exits


def test_correlation_rejects_on_entry_only(redirect_decision_audit):
    manager, config = make_manager()
    corr = CorrelationCheckResult(exceeded=True, max_correlation=0.9, correlated_symbol="ETH/USD")
    decision = manager.check_pre_trade(base_ctx(correlation_result=corr))
    assert not decision.approved
    assert decision.checks[-1].name == "correlation"

    exit_decision = manager.check_pre_trade(base_ctx(is_entry=False, correlation_result=corr))
    assert exit_decision.approved


def test_regime_filter_rejects(redirect_decision_audit):
    manager, _ = make_manager()
    decision = manager.check_pre_trade(base_ctx(regime_ok=False))
    assert not decision.approved
    assert decision.checks[-1].name == "regime_filter"


def test_position_sizing_rejection_propagates(redirect_decision_audit):
    manager, _ = make_manager()
    # win_probability too low -> negative Kelly -> sizing rejected
    decision = manager.check_pre_trade(base_ctx(win_probability=0.3, win_loss_ratio=1.0))
    assert not decision.approved
    assert decision.checks[-1].name == "position_sizing"
    assert decision.position_sizing is not None
    assert decision.position_sizing.rejected


def test_position_sizing_never_blocks_an_exit(redirect_decision_audit):
    # An exit's execution quantity comes from the caller's actual open
    # position, not a fresh Kelly calculation — an unfavorable win_probability
    # must never prevent getting out of a position.
    manager, _ = make_manager()
    decision = manager.check_pre_trade(
        base_ctx(is_entry=False, win_probability=0.1, win_loss_ratio=1.0)
    )
    assert decision.approved
    sizing_check = next(c for c in decision.checks if c.name == "position_sizing")
    assert sizing_check.passed
    assert decision.position_sizing is None


def test_gross_exposure_rejects_on_entry(redirect_decision_audit):
    manager, config = make_manager()
    decision = manager.check_pre_trade(
        base_ctx(current_gross_exposure=config.max_gross_exposure)
    )
    assert not decision.approved
    assert decision.checks[-1].name == "gross_exposure"


def test_capital_allocation_rejects(redirect_decision_audit):
    manager, _ = make_manager()
    decision = manager.check_pre_trade(base_ctx(capital_allocation_ok=False))
    assert not decision.approved
    assert decision.checks[-1].name == "capital_allocation"


def test_minimum_portfolio_rejects(redirect_decision_audit):
    manager, _ = make_manager()
    decision = manager.check_pre_trade(base_ctx(portfolio_value=500.0))
    assert not decision.approved
    assert decision.checks[-1].name == "minimum_portfolio"


def test_connector_health_rejects_last(redirect_decision_audit):
    manager, _ = make_manager()
    decision = manager.check_pre_trade(base_ctx(connector_healthy=False))
    assert not decision.approved
    assert decision.checks[-1].name == "connector_health"
    assert [c.name for c in decision.checks] == list(CHECK_ORDER)  # ran every prior check


def test_safe_mode_blocks_entries_but_allows_exits(redirect_decision_audit):
    manager, config = make_manager()
    manager.safe_mode.activate("drawdown_ceiling", halt_new_entries=True, requires_manual_restart=True, now=NOW)

    entry_decision = manager.check_pre_trade(base_ctx())
    assert not entry_decision.approved
    assert entry_decision.checks[-1].name == "safe_mode"

    exit_decision = manager.check_pre_trade(base_ctx(is_entry=False))
    assert exit_decision.checks[0].name == "strategy_status"
    assert exit_decision.checks[1].passed  # safe_mode check passes for exits


def test_decision_audit_written_as_jsonl(redirect_decision_audit):
    manager, _ = make_manager()
    manager.check_pre_trade(base_ctx())
    manager.check_pre_trade(base_ctx(strategy_enabled=False))

    lines = redirect_decision_audit.read_text().strip().splitlines()
    assert len(lines) == 2
    record = json.loads(lines[0])
    assert record["asset"] == "BTC/USD"
    assert "checks" in record and isinstance(record["checks"], list)
