"""In-process backtest runner (DOC 3 §9). Replays bars in strict chronological
order and executes every signal at the *next* bar's open — a signal generated
from bar[i] can only affect bar[i+1] onward, which is what prevents look-ahead
bias (the strategy only ever sees data up to and including the current bar).

Position accounting uses a single unified rule: every fill is a signed
`delta_quantity` (positive = buy, negative = sell) at a fill price; cash moves
by `-delta_quantity * fill_price - fee` regardless of whether the fill opens,
adds to, or closes a long or short position. This one rule correctly handles
both directions without separate long/short bookkeeping.

Only one open position per asset is modeled at a time — an entry signal for
an asset that already has a position is ignored (this mirrors the Engine's
own max_concurrent_positions / no-pyramiding behavior, so backtests match how
the live Engine will actually behave for a given strategy).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from common.enums import Direction
from engine.backtest.cost_model import TransactionCostModel
from engine.backtest.metrics import compute_metrics
from engine.backtest.types import BacktestResult, Trade
from sdk.ate_smp.models.bar import Bar
from sdk.ate_smp.strategy_base import StrategyBase


class LookAheadBiasError(ValueError):
    """Raised when bars are not in strict chronological order."""


@dataclass
class _OpenPosition:
    asset: str
    side: str  # "long" | "short"
    quantity: float  # absolute size
    entry_time: datetime
    entry_price: float
    entry_fee: float


class BacktestRunner:
    def __init__(
        self,
        cost_model: TransactionCostModel,
        position_fraction: float = 1.0,
        risk_free_rate: float = 0.0,
        periods_per_year: int = 252,
    ) -> None:
        self.cost_model = cost_model
        self.position_fraction = position_fraction
        self.risk_free_rate = risk_free_rate
        self.periods_per_year = periods_per_year

    def run(self, strategy: StrategyBase, bars: list[Bar], initial_capital: float) -> BacktestResult:
        if initial_capital <= 0:
            raise ValueError(f"initial_capital {initial_capital} must be positive")
        self._assert_chronological(bars)

        cash = initial_capital
        positions: dict[str, _OpenPosition] = {}
        open_trades: dict[str, Trade] = {}
        closed_trades: list[Trade] = []
        equity_curve: list[tuple[datetime, float]] = []
        last_price: dict[str, float] = {}
        pending_signals = []

        for bar in bars:
            if pending_signals:
                for signal in pending_signals:
                    cash = self._execute_signal(
                        signal, bar, cash, positions, open_trades, closed_trades
                    )
                pending_signals = []

            last_price[bar.asset] = bar.close
            equity = self._mark_to_market(cash, positions, last_price)
            equity_curve.append((bar.timestamp, equity))

            signals = strategy.on_bar(bar)
            pending_signals.extend(signals)

        metrics = compute_metrics(equity_curve, closed_trades, self.risk_free_rate, self.periods_per_year)
        final_equity = equity_curve[-1][1] if equity_curve else initial_capital

        return BacktestResult(
            equity_curve=equity_curve,
            trades=closed_trades,
            final_equity=final_equity,
            metrics=metrics,
        )

    @staticmethod
    def _assert_chronological(bars: list[Bar]) -> None:
        for i in range(1, len(bars)):
            if bars[i].timestamp < bars[i - 1].timestamp:
                raise LookAheadBiasError(
                    f"bars not in chronological order at index {i}: "
                    f"{bars[i].timestamp} < {bars[i - 1].timestamp}"
                )

    @staticmethod
    def _signed_quantity(position: _OpenPosition) -> float:
        return position.quantity if position.side == "long" else -position.quantity

    def _mark_to_market(
        self, cash: float, positions: dict[str, _OpenPosition], last_price: dict[str, float]
    ) -> float:
        equity = cash
        for position in positions.values():
            price = last_price.get(position.asset, position.entry_price)
            equity += self._signed_quantity(position) * price
        return equity

    def _execute_signal(
        self,
        signal,
        bar: Bar,
        cash: float,
        positions: dict[str, _OpenPosition],
        open_trades: dict[str, Trade],
        closed_trades: list[Trade],
    ) -> float:
        if signal.asset != bar.asset:
            return cash  # this bar isn't for this signal's asset; nothing to fill yet

        existing = positions.get(signal.asset)

        if signal.direction in (Direction.LONG, Direction.SHORT):
            if existing is not None:
                return cash  # no pyramiding: ignore new entries while a position is open

            is_buy = signal.direction == Direction.LONG
            fill_price = self.cost_model.apply_slippage(bar.open, is_buy=is_buy, bar_volume=bar.volume)
            notional = cash * self.position_fraction * max(0.0, min(1.0, signal.strength))
            if notional <= 0 or fill_price <= 0:
                return cash
            quantity = notional / fill_price
            fee = self.cost_model.compute_fee(notional, quantity)
            delta = quantity if is_buy else -quantity

            cash -= delta * fill_price + fee

            side = "long" if is_buy else "short"
            positions[signal.asset] = _OpenPosition(
                asset=signal.asset,
                side=side,
                quantity=quantity,
                entry_time=bar.timestamp,
                entry_price=fill_price,
                entry_fee=fee,
            )
            open_trades[signal.asset] = Trade(
                asset=signal.asset,
                side=side,
                quantity=quantity,
                entry_time=bar.timestamp,
                entry_price=fill_price,
                entry_fee=fee,
            )
            return cash

        if signal.direction in (Direction.EXIT_LONG, Direction.EXIT_SHORT, Direction.FLATTEN):
            if existing is None:
                return cash
            if signal.direction == Direction.EXIT_LONG and existing.side != "long":
                return cash
            if signal.direction == Direction.EXIT_SHORT and existing.side != "short":
                return cash

            is_buy_to_close = existing.side == "short"  # closing a short = buying back
            fill_price = self.cost_model.apply_slippage(
                bar.open, is_buy=is_buy_to_close, bar_volume=bar.volume
            )
            notional = existing.quantity * fill_price
            fee = self.cost_model.compute_fee(notional, existing.quantity)
            delta = -self._signed_quantity(existing)  # closes the position exactly

            cash -= delta * fill_price + fee

            trade = open_trades.pop(existing.asset)
            trade.exit_time = bar.timestamp
            trade.exit_price = fill_price
            trade.exit_fee = fee
            closed_trades.append(trade)

            del positions[existing.asset]
            return cash

        return cash
