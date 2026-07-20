from datetime import datetime, timedelta, timezone

import pytest

from engine.backtest.metrics import (
    compute_metrics,
    equity_returns,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
    total_return,
    win_rate,
)
from engine.backtest.types import Trade

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def curve(values):
    return [(T0 + timedelta(days=i), v) for i, v in enumerate(values)]


def make_trade(pnl_target: float, entry_price=100.0, side="long") -> Trade:
    trade = Trade(
        asset="BTC/USD", side=side, quantity=1.0, entry_time=T0, entry_price=entry_price, entry_fee=0.0
    )
    trade.exit_time = T0 + timedelta(days=1)
    trade.exit_price = entry_price + pnl_target if side == "long" else entry_price - pnl_target
    trade.exit_fee = 0.0
    return trade


def test_equity_returns_basic():
    returns = equity_returns(curve([100, 110, 121]))
    assert returns == pytest.approx([0.10, 0.10])


def test_equity_returns_skips_zero_denominator():
    returns = equity_returns(curve([0, 100]))
    assert returns == []


def test_sharpe_ratio_zero_with_insufficient_data():
    assert sharpe_ratio([0.01]) == 0.0
    assert sharpe_ratio([]) == 0.0


def test_sharpe_ratio_zero_with_no_variance():
    assert sharpe_ratio([0.01, 0.01, 0.01]) == 0.0


def test_sharpe_ratio_positive_for_positive_mean_returns():
    assert sharpe_ratio([0.01, 0.02, 0.015, 0.005]) > 0


def test_max_drawdown_basic():
    dd = max_drawdown(curve([100, 120, 90, 130]))
    assert dd == pytest.approx((120 - 90) / 120)


def test_max_drawdown_zero_for_monotonic_increase():
    assert max_drawdown(curve([100, 110, 120])) == 0.0


def test_win_rate_and_profit_factor():
    trades = [make_trade(10), make_trade(-5), make_trade(20)]
    assert win_rate(trades) == pytest.approx(2 / 3)
    assert profit_factor(trades) == pytest.approx(30 / 5)


def test_win_rate_empty_trades():
    assert win_rate([]) == 0.0


def test_profit_factor_no_losses_is_infinite():
    trades = [make_trade(10), make_trade(5)]
    assert profit_factor(trades) == float("inf")


def test_profit_factor_no_trades_is_zero():
    assert profit_factor([]) == 0.0


def test_win_rate_ignores_open_trades():
    open_trade = Trade(asset="BTC/USD", side="long", quantity=1, entry_time=T0, entry_price=100, entry_fee=0)
    trades = [make_trade(10), open_trade]
    assert win_rate(trades) == 1.0  # only the closed trade counts


def test_total_return():
    assert total_return(curve([100, 150])) == pytest.approx(0.5)
    assert total_return([]) == 0.0


def test_compute_metrics_bundles_everything():
    trades = [make_trade(10), make_trade(-5)]
    metrics = compute_metrics(curve([100, 105, 110]), trades)
    assert set(metrics.keys()) == {
        "sharpe", "max_drawdown", "win_rate", "profit_factor", "total_return", "num_trades"
    }
    assert metrics["num_trades"] == 2
