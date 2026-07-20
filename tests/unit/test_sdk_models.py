from datetime import datetime, timezone

import pytest

from common.enums import AssetClass, Direction, ParameterType, Timeframe
from sdk.ate_smp.models.bar import Bar, Tick
from sdk.ate_smp.models.signal import Signal
from sdk.ate_smp.models.strategy_config import ParameterDefinition, StrategyConfig

NOW = datetime.now(timezone.utc)


def test_bar_accepts_valid_ohlc():
    bar = Bar(
        asset="BTC/USD",
        timeframe=Timeframe.H1,
        timestamp=NOW,
        open=100,
        high=110,
        low=95,
        close=105,
        volume=10,
    )
    assert bar.high >= bar.low


@pytest.mark.parametrize(
    "open_,high,low,close,volume",
    [
        (100, 90, 95, 100, 10),  # high < low
        (200, 110, 95, 100, 10),  # open outside range
        (100, 110, 95, 200, 10),  # close outside range
        (100, 110, 95, 100, -1),  # negative volume
    ],
)
def test_bar_rejects_invalid_ohlc(open_, high, low, close, volume):
    with pytest.raises(ValueError):
        Bar(
            asset="BTC/USD",
            timeframe=Timeframe.H1,
            timestamp=NOW,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
        )


def test_tick_rejects_nonpositive_price():
    with pytest.raises(ValueError):
        Tick(asset="BTC/USD", timestamp=NOW, price=0, size=1)


def test_signal_strength_bounds():
    Signal(timestamp=NOW, asset="BTC/USD", direction=Direction.LONG, strength=1.0)
    with pytest.raises(ValueError):
        Signal(timestamp=NOW, asset="BTC/USD", direction=Direction.LONG, strength=1.5)
    with pytest.raises(ValueError):
        Signal(timestamp=NOW, asset="BTC/USD", direction=Direction.LONG, strength=-0.1)


def test_signal_rejects_nonpositive_limit_price():
    with pytest.raises(ValueError):
        Signal(
            timestamp=NOW,
            asset="BTC/USD",
            direction=Direction.LONG,
            strength=0.5,
            limit_price=0,
        )


def test_strategy_config_requires_symbols_and_timeframes():
    with pytest.raises(ValueError):
        StrategyConfig(asset_class=AssetClass.CRYPTO, symbols=(), timeframes=(Timeframe.H1,))
    with pytest.raises(ValueError):
        StrategyConfig(asset_class=AssetClass.CRYPTO, symbols=("BTC/USD",), timeframes=())


def test_strategy_config_capital_allocation_bounds():
    with pytest.raises(ValueError):
        StrategyConfig(
            asset_class=AssetClass.CRYPTO,
            symbols=("BTC/USD",),
            timeframes=(Timeframe.H1,),
            capital_allocation=0.0,
        )
    with pytest.raises(ValueError):
        StrategyConfig(
            asset_class=AssetClass.CRYPTO,
            symbols=("BTC/USD",),
            timeframes=(Timeframe.H1,),
            capital_allocation=1.5,
        )


def test_parameter_definition_enum_requires_choices():
    with pytest.raises(ValueError):
        ParameterDefinition(name="mode", type=ParameterType.ENUM, default="a", choices=None)
    ParameterDefinition(name="mode", type=ParameterType.ENUM, default="a", choices=("a", "b"))
