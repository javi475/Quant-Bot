from datetime import datetime, timedelta, timezone

import pytest

from engine.backtest.monte_carlo import MonteCarloSimulator
from engine.backtest.types import Trade

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_trade(pnl: float) -> Trade:
    trade = Trade(asset="BTC/USD", side="long", quantity=1.0, entry_time=T0, entry_price=100.0, entry_fee=0.0)
    trade.exit_time = T0 + timedelta(days=1)
    trade.exit_price = 100.0 + pnl
    trade.exit_fee = 0.0
    return trade


def test_deterministic_with_fixed_seed():
    trades = [make_trade(p) for p in [100, -50, 200, -80, 60]]
    sim = MonteCarloSimulator(iterations=200, random_seed=42)
    result_a = sim.run(trades, initial_capital=10_000)
    result_b = MonteCarloSimulator(iterations=200, random_seed=42).run(trades, initial_capital=10_000)
    assert result_a.percentile_curves == result_b.percentile_curves
    assert result_a.prob_of_ruin == result_b.prob_of_ruin


def test_percentile_curves_monotonic_at_every_step():
    trades = [make_trade(p) for p in [100, -50, 200, -80, 60, -30, 150]]
    result = MonteCarloSimulator(iterations=300, random_seed=1).run(trades, initial_capital=10_000)
    p5, p50, p95 = result.percentile_curves["p5"], result.percentile_curves["p50"], result.percentile_curves["p95"]
    assert len(p5) == len(p50) == len(p95) == len(trades) + 1
    for a, b, c in zip(p5, p50, p95):
        assert a <= b <= c


def test_guaranteed_ruin_detected():
    trades = [make_trade(-9000)]  # single trade wipes out 90% of a 10k account
    result = MonteCarloSimulator(iterations=100, ruin_threshold=0.5, random_seed=1).run(
        trades, initial_capital=10_000
    )
    assert result.prob_of_ruin == 1.0


def test_no_ruin_when_all_trades_profitable():
    trades = [make_trade(p) for p in [10, 20, 30]]
    result = MonteCarloSimulator(iterations=100, random_seed=1).run(trades, initial_capital=10_000)
    assert result.prob_of_ruin == 0.0


def test_returns_resampling_method_runs():
    trades = [make_trade(p) for p in [10, -5, 20]]
    result = MonteCarloSimulator(iterations=50, resampling="returns", random_seed=1).run(
        trades, initial_capital=10_000
    )
    assert result.iterations == 50


def test_rejects_unknown_resampling_method():
    with pytest.raises(ValueError):
        MonteCarloSimulator(resampling="bogus")


def test_rejects_empty_trades():
    with pytest.raises(ValueError):
        MonteCarloSimulator(iterations=10).run([], initial_capital=10_000)


def test_rejects_nonpositive_capital():
    trades = [make_trade(10)]
    with pytest.raises(ValueError):
        MonteCarloSimulator(iterations=10).run(trades, initial_capital=0)


def test_ignores_open_trades():
    open_trade = Trade(asset="BTC/USD", side="long", quantity=1, entry_time=T0, entry_price=100, entry_fee=0)
    trades = [make_trade(10), open_trade]
    result = MonteCarloSimulator(iterations=20, random_seed=1).run(trades, initial_capital=10_000)
    assert len(result.percentile_curves["p50"]) == 2  # only the one closed trade
