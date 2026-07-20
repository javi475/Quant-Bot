"""Reference strategy implementation (DOC 3 §1): RSI(2) mean-reversion, gated
by Bollinger Bands and an ADX trend filter so entries only fire in
non-trending regimes. This is a didactic example for the SDK/sandbox, not a
production-validated strategy — it must still pass a full backtest gate
(DOC 7 §3) before any live deployment.

Only sandbox-allowed imports are used: math, statistics, collections, typing,
and the ate_smp SDK itself (DOC 3 §6 allow-list).
"""

from __future__ import annotations

import statistics
from collections import deque
from typing import Any

from ate_smp import (
    Bar,
    Direction,
    FillNotification,
    ParameterDefinition,
    ParameterType,
    Signal,
    StrategyBase,
    StrategyConfig,
    Tick,
)


class RsiMeanReversionStrategy(StrategyBase):
    def __init__(self) -> None:
        super().__init__()
        self._params: dict[str, Any] = {}
        self._closes: dict[str, deque[float]] = {}
        self._highs: dict[str, deque[float]] = {}
        self._lows: dict[str, deque[float]] = {}
        self._in_position: dict[str, bool] = {}

    def initialize(self, config: StrategyConfig) -> None:
        self.config = config
        defaults = {d.name: d.default for d in self.get_parameters_schema()}
        self._params = {**defaults, **config.parameters}

        max_len = max(self._params["bb_period"], self._params["adx_period"] + 1) + 1
        for symbol in config.symbols:
            self._closes[symbol] = deque(maxlen=max_len)
            self._highs[symbol] = deque(maxlen=max_len)
            self._lows[symbol] = deque(maxlen=max_len)
            self._in_position[symbol] = False

    def get_parameters_schema(self) -> list[ParameterDefinition]:
        return [
            ParameterDefinition(
                name="rsi_period",
                type=ParameterType.INTEGER,
                default=2,
                min=1,
                max=10,
                group="entry",
                description="RSI lookback period",
            ),
            ParameterDefinition(
                name="oversold",
                type=ParameterType.FLOAT,
                default=10.0,
                min=1.0,
                max=30.0,
                group="entry",
                description="RSI level below which a long entry is considered",
            ),
            ParameterDefinition(
                name="overbought",
                type=ParameterType.FLOAT,
                default=90.0,
                min=70.0,
                max=99.0,
                group="exit",
                description="RSI level above which the position is exited",
            ),
            ParameterDefinition(
                name="bb_period",
                type=ParameterType.INTEGER,
                default=20,
                min=10,
                max=50,
                group="entry",
                description="Bollinger Band lookback period",
            ),
            ParameterDefinition(
                name="bb_std",
                type=ParameterType.FLOAT,
                default=2.0,
                min=1.0,
                max=3.0,
                group="entry",
                description="Bollinger Band standard deviation multiplier",
            ),
            ParameterDefinition(
                name="adx_period",
                type=ParameterType.INTEGER,
                default=14,
                min=5,
                max=30,
                group="filter",
                description="ADX lookback period",
            ),
            ParameterDefinition(
                name="adx_threshold",
                type=ParameterType.FLOAT,
                default=25.0,
                min=10.0,
                max=40.0,
                group="filter",
                description="Only take mean-reversion entries when ADX is below this (non-trending)",
            ),
        ]

    def on_bar(self, bar: Bar) -> list[Signal]:
        symbol = bar.asset
        if symbol not in self._closes:
            return []

        closes, highs, lows = self._closes[symbol], self._highs[symbol], self._lows[symbol]
        closes.append(bar.close)
        highs.append(bar.high)
        lows.append(bar.low)

        rsi_period = self._params["rsi_period"]
        bb_period = self._params["bb_period"]
        adx_period = self._params["adx_period"]

        if len(closes) < max(rsi_period + 1, bb_period, adx_period + 1):
            return []

        rsi = self._compute_rsi(list(closes), rsi_period)
        bb_mid, bb_lower, bb_upper = self._compute_bollinger(
            list(closes)[-bb_period:], self._params["bb_std"]
        )
        adx = self._compute_adx(list(highs), list(lows), list(closes), adx_period)

        signals: list[Signal] = []
        in_position = self._in_position[symbol]

        if not in_position:
            if (
                rsi <= self._params["oversold"]
                and bar.close <= bb_lower
                and adx <= self._params["adx_threshold"]
            ):
                signals.append(
                    Signal(
                        timestamp=bar.timestamp,
                        asset=symbol,
                        direction=Direction.LONG,
                        strength=min(1.0, (self._params["oversold"] - rsi) / self._params["oversold"] + 0.5),
                        metadata={"rsi": rsi, "adx": adx, "bb_lower": bb_lower},
                    )
                )
                self._in_position[symbol] = True
        else:
            if rsi >= self._params["overbought"] or bar.close >= bb_mid:
                signals.append(
                    Signal(
                        timestamp=bar.timestamp,
                        asset=symbol,
                        direction=Direction.EXIT_LONG,
                        strength=1.0,
                        metadata={"rsi": rsi, "bb_mid": bb_mid},
                    )
                )
                self._in_position[symbol] = False

        return signals

    def on_tick(self, tick: Tick) -> list[Signal]:
        return []

    def on_fill(self, fill: FillNotification) -> None:
        pass

    def get_win_probability(self) -> float:
        return 0.55

    def get_win_loss_ratio(self) -> float:
        return 1.5

    def get_state(self) -> dict[str, Any]:
        return {
            "closes": {k: list(v) for k, v in self._closes.items()},
            "highs": {k: list(v) for k, v in self._highs.items()},
            "lows": {k: list(v) for k, v in self._lows.items()},
            "in_position": dict(self._in_position),
        }

    def set_state(self, state: dict[str, Any]) -> None:
        max_len = max(self._params.get("bb_period", 20), self._params.get("adx_period", 14) + 1) + 1
        for symbol, values in state.get("closes", {}).items():
            self._closes[symbol] = deque(values, maxlen=max_len)
        for symbol, values in state.get("highs", {}).items():
            self._highs[symbol] = deque(values, maxlen=max_len)
        for symbol, values in state.get("lows", {}).items():
            self._lows[symbol] = deque(values, maxlen=max_len)
        self._in_position.update(state.get("in_position", {}))

    # ----- Indicator helpers -----

    @staticmethod
    def _compute_rsi(closes: list[float], period: int) -> float:
        window = closes[-(period + 1) :]
        deltas = [window[i] - window[i - 1] for i in range(1, len(window))]
        gains = [d for d in deltas if d > 0]
        losses = [-d for d in deltas if d < 0]
        avg_gain = sum(gains) / period if gains else 0.0
        avg_loss = sum(losses) / period if losses else 0.0
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def _compute_bollinger(window: list[float], num_std: float) -> tuple[float, float, float]:
        mean = statistics.mean(window)
        std = statistics.pstdev(window) if len(window) > 1 else 0.0
        return mean, mean - num_std * std, mean + num_std * std

    @staticmethod
    def _compute_adx(highs: list[float], lows: list[float], closes: list[float], period: int) -> float:
        window = period + 1
        h, l, c = highs[-window:], lows[-window:], closes[-window:]

        plus_dm, minus_dm, tr = [], [], []
        for i in range(1, len(h)):
            up_move = h[i] - h[i - 1]
            down_move = l[i - 1] - l[i]
            plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
            minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
            tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))

        atr = sum(tr) / period if tr else 0.0
        if atr == 0:
            return 0.0

        plus_di = 100.0 * (sum(plus_dm) / period) / atr
        minus_di = 100.0 * (sum(minus_dm) / period) / atr
        di_sum = plus_di + minus_di
        if di_sum == 0:
            return 0.0
        dx = 100.0 * abs(plus_di - minus_di) / di_sum
        return dx
