"""Correlation cap (DOC 4 §6): rejects a new entry if its rolling daily returns
are too correlated with any existing open position. Missing/insufficient
history for a pair is tolerated (allowed through) rather than blocking the
trade, per spec."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Optional

from engine.risk.risk_config import RiskConfig

MIN_OBSERVATIONS = 2


@dataclass(frozen=True)
class CorrelationCheckResult:
    exceeded: bool
    max_correlation: float
    correlated_symbol: Optional[str]


class CorrelationManager:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config

    def check_correlation(
        self,
        new_returns: list[float],
        existing_positions_returns: dict[str, list[float]],
    ) -> CorrelationCheckResult:
        max_abs_corr = 0.0
        max_corr_value = 0.0
        max_corr_symbol: Optional[str] = None

        for symbol, returns in existing_positions_returns.items():
            n = min(len(returns), len(new_returns))
            if n < MIN_OBSERVATIONS:
                continue  # insufficient data for this pair -> allow, skip

            try:
                corr = statistics.correlation(new_returns[-n:], returns[-n:])
            except statistics.StatisticsError:
                continue  # e.g. zero variance in one series -> allow, skip

            if abs(corr) > max_abs_corr:
                max_abs_corr = abs(corr)
                max_corr_value = corr
                max_corr_symbol = symbol

        exceeded = max_abs_corr > self.config.correlation_cap
        return CorrelationCheckResult(
            exceeded=exceeded, max_correlation=max_corr_value, correlated_symbol=max_corr_symbol
        )
