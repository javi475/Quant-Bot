"""Kelly-criterion position sizing (DOC 4 §1).

Pipeline: full Kelly f* = (p*(b+1) - 1) / b  ->  clamp negative to 0  ->
x0.25 kelly_multiplier  ->  x signal_strength  ->  x safe_mode multiplier  ->
cap at max_risk_per_trade (2%)  ->  position_value = f_applied * portfolio_value,
quantity = position_value / price.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from engine.risk.risk_config import RiskConfig

MIN_PROBABILITY = 0.001
MAX_PROBABILITY = 0.999


@dataclass(frozen=True)
class PositionSizeResult:
    quantity: float
    position_value: float
    kelly_fraction_full: float
    kelly_fraction_applied: float
    rejected: bool
    rejection_reason: Optional[str] = None


class PositionSizer:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config

    def calculate_size(
        self,
        win_probability: float,
        win_loss_ratio: float,
        signal_strength: float,
        portfolio_value: float,
        price: float,
        safe_mode_multiplier: float = 1.0,
    ) -> PositionSizeResult:
        if portfolio_value <= 0:
            raise ValueError(f"portfolio_value {portfolio_value} must be positive")
        if price <= 0:
            raise ValueError(f"price {price} must be positive")

        p = min(max(win_probability, 0.0), 1.0)
        p = min(max(p, MIN_PROBABILITY), MAX_PROBABILITY)

        # Note: the $min_portfolio_value business-rule rejection lives in
        # RiskManager step 12 ("minimum_portfolio"), which runs *after* this
        # step in the pipeline (DOC 4 §9) — duplicating it here would always
        # shadow that check's rationale in the audit log.

        if signal_strength <= 0:
            return self._rejected("signal strength must be positive")

        if win_loss_ratio == 0:
            # Division by zero in the Kelly formula: treated as a non-positive
            # fraction rather than falling back to the invalid-input default.
            return self._rejected("Kelly fraction non-positive (win_loss_ratio is zero)")
        b = win_loss_ratio if win_loss_ratio is not None and win_loss_ratio > 0 else 1.0

        full_kelly = (p * (b + 1) - 1) / b
        clamped_full_kelly = max(full_kelly, 0.0)

        if clamped_full_kelly <= 0:
            return self._rejected("Kelly fraction non-positive", kelly_fraction_full=full_kelly)

        applied = clamped_full_kelly * self.config.kelly_multiplier * signal_strength * safe_mode_multiplier
        applied = min(applied, self.config.max_risk_per_trade)

        if applied <= 0:
            return self._rejected(
                "applied Kelly fraction non-positive after safe-mode/strength scaling",
                kelly_fraction_full=full_kelly,
            )

        position_value = applied * portfolio_value
        quantity = position_value / price

        return PositionSizeResult(
            quantity=quantity,
            position_value=position_value,
            kelly_fraction_full=full_kelly,
            kelly_fraction_applied=applied,
            rejected=False,
        )

    @staticmethod
    def _rejected(reason: str, kelly_fraction_full: float = 0.0) -> PositionSizeResult:
        return PositionSizeResult(
            quantity=0.0,
            position_value=0.0,
            kelly_fraction_full=kelly_fraction_full,
            kelly_fraction_applied=0.0,
            rejected=True,
            rejection_reason=reason,
        )

    def calculate_implied_stop_loss(
        self, entry_price: float, is_long: bool, portfolio_value: float, quantity: float
    ) -> float:
        """For strategies that don't declare an explicit stop, derives the price
        at which the position's loss would equal max_risk_per_trade (DOC 4 §4)."""
        if entry_price <= 0 or portfolio_value <= 0 or quantity <= 0:
            raise ValueError("entry_price, portfolio_value, and quantity must be positive")

        max_loss_value = self.config.max_risk_per_trade * portfolio_value
        price_move = max_loss_value / quantity

        return entry_price - price_move if is_long else entry_price + price_move
