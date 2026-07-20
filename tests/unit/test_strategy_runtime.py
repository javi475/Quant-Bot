"""Integration-style tests that spawn a real strategy subprocess and drive it
over the JSON-Lines IPC protocol (DOC 2 §5, DOC 3 §11)."""

import os
from datetime import datetime, timezone

import pytest

from ate_smp.models.bar import Bar
from ate_smp.models.strategy_config import StrategyConfig
from common.enums import AssetClass, Timeframe
from engine.strategy import serialization as ser
from engine.strategy.runtime import StrategyCrashedError, StrategyProcess, StrategyTimeoutError

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
REFERENCE_STRATEGY_PATH = os.path.join(
    REPO_ROOT, "example_strategies", "rsi_mean_reversion.py"
)

BUSY_LOOP_STRATEGY_SOURCE = """
from ate_smp import StrategyBase

class SlowStrategy(StrategyBase):
    def initialize(self, config):
        pass
    def on_bar(self, bar):
        total = 0
        for i in range(300_000_000):
            total += i
        return []
    def on_tick(self, tick):
        return []
    def on_fill(self, fill):
        pass
    def get_parameters_schema(self):
        return []
    def get_win_probability(self):
        return 0.5
    def get_win_loss_ratio(self):
        return 1.0
    def get_state(self):
        return {}
    def set_state(self, state):
        pass
"""


def make_config() -> StrategyConfig:
    return StrategyConfig(
        asset_class=AssetClass.CRYPTO,
        symbols=("BTC/USD",),
        timeframes=(Timeframe.H1,),
    )


@pytest.fixture
async def reference_process():
    process = StrategyProcess("test-rsi", REFERENCE_STRATEGY_PATH, "RsiMeanReversionStrategy")
    await process.start()
    yield process
    await process.shutdown()


async def test_initialize_and_on_bar_roundtrip(reference_process):
    await reference_process.initialize(make_config())

    signals = []
    for i in range(30):
        bar = Bar(
            asset="BTC/USD",
            timeframe=Timeframe.H1,
            timestamp=datetime.now(timezone.utc),
            open=100.0,
            high=100.5,
            low=99.5,
            close=100.0,
            volume=1.0,
        )
        signals.extend(await reference_process.on_bar(bar))

    assert isinstance(signals, list)


async def test_state_roundtrip_over_ipc(reference_process):
    await reference_process.initialize(make_config())
    state_before = await reference_process.get_state()
    await reference_process.set_state(state_before)
    state_after = await reference_process.get_state()
    assert state_after == state_before


async def test_get_parameters_schema_over_ipc(reference_process):
    schema = await reference_process.get_parameters_schema()
    names = {d.name for d in schema}
    assert "rsi_period" in names


async def test_slow_strategy_triggers_timeout(tmp_path):
    strategy_file = tmp_path / "slow_strategy.py"
    strategy_file.write_text(BUSY_LOOP_STRATEGY_SOURCE)

    process = StrategyProcess("test-slow", str(strategy_file), "SlowStrategy")
    await process.start()
    try:
        await process.initialize(make_config())
        bar = Bar(
            asset="BTC/USD",
            timeframe=Timeframe.H1,
            timestamp=datetime.now(timezone.utc),
            open=100.0,
            high=100.5,
            low=99.5,
            close=100.0,
            volume=1.0,
        )
        with pytest.raises(StrategyTimeoutError):
            await process._call("on_bar", {"bar": ser.encode_bar(bar)}, timeout=0.05)
    finally:
        await process.kill()


async def test_invalid_strategy_class_reports_crash():
    process = StrategyProcess("test-bad", REFERENCE_STRATEGY_PATH, "NoSuchClass")
    await process.start()
    with pytest.raises(StrategyCrashedError):
        await process.initialize(make_config())
    await process.kill()
