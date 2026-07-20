import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "example_strategies"))

from ate_smp import AssetClass, Direction, StrategyConfig, Timeframe
from ate_smp.testing import StrategyTestRunner
from rsi_mean_reversion import RsiMeanReversionStrategy


def make_runner(**parameters) -> StrategyTestRunner:
    strategy = RsiMeanReversionStrategy()
    config = StrategyConfig(
        asset_class=AssetClass.CRYPTO,
        symbols=("BTC/USD",),
        timeframes=(Timeframe.H1,),
        parameters=parameters,
    )
    return StrategyTestRunner(strategy, config)


def test_schema_is_well_formed():
    runner = make_runner()
    runner.validate_schema()
    names = {d.name for d in runner.strategy.get_parameters_schema()}
    assert {"rsi_period", "bb_period", "adx_period", "oversold", "overbought"}.issubset(names)


def test_state_roundtrip_after_warmup():
    runner = make_runner()
    bars = runner.make_series([100 + (i % 5) for i in range(30)])
    runner.run(bars)
    runner.validate_state_roundtrip()


def test_dip_then_recovery_produces_long_then_exit():
    # ADX threshold is loosened to isolate the RSI/Bollinger entry-exit logic
    # from the trend filter: a sudden regime change after a flat warmup
    # spikes ADX to its max (correctly, per DOC 3 — this filter exists so the
    # strategy skips mean-reversion entries during strong trends), which
    # would otherwise mask the signal logic under test here.
    runner = make_runner(adx_threshold=100.0)
    # Flat warmup, then a sharp dip (oversold + below lower band), then a
    # recovery back toward the mean — should produce a LONG then an EXIT_LONG.
    closes = [100.0] * 25 + [95, 90, 85, 80] + [85, 92, 100, 105, 110]
    bars = runner.make_series(closes)
    results = runner.run(bars)

    directions = [s.direction for signals in results for s in signals]
    assert directions == [Direction.LONG, Direction.EXIT_LONG]


def test_adx_filter_blocks_entry_during_strong_trend():
    # Same dip/recovery shape but with the default (strict) adx_threshold:
    # the sudden trend after a flat warmup should suppress the entry.
    runner = make_runner()
    closes = [100.0] * 25 + [95, 90, 85, 80] + [85, 92, 100, 105, 110]
    bars = runner.make_series(closes)
    results = runner.run(bars)

    directions = [s.direction for signals in results for s in signals]
    assert Direction.LONG not in directions


def test_on_bar_returns_empty_before_warmup():
    runner = make_runner()
    bars = runner.make_series([100.0, 101.0, 99.0])
    results = runner.run(bars)
    assert all(signals == [] for signals in results)
