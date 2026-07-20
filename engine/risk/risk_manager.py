"""Pre-trade risk check pipeline (DOC 4 §9): 13 sequential checks, each
logged with its rationale to the immutable decision audit trail. The first
failing check rejects the trade; every check still ran up to that point is
recorded in the RiskDecision returned to the caller (and to the audit log).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from common.logging_config import decision_audit_path
from engine.risk.correlation import CorrelationCheckResult
from engine.risk.position_sizer import PositionSizeResult, PositionSizer
from engine.risk.risk_config import RiskConfig
from engine.risk.safe_mode import SafeModeManager

CHECK_ORDER = (
    "strategy_status",
    "safe_mode",
    "daily_loss_breaker",
    "drawdown_ceiling",
    "position_limit",
    "correlation",
    "regime_filter",
    "position_sizing",
    "gross_exposure",
    "leverage",
    "capital_allocation",
    "minimum_portfolio",
    "connector_health",
)


@dataclass(frozen=True)
class RiskCheckResult:
    name: str
    passed: bool
    detail: Optional[str] = None


@dataclass(frozen=True)
class PreTradeContext:
    asset: str
    is_entry: bool
    strategy_enabled: bool
    trading_mode_ok: bool
    now: datetime
    portfolio_value: float
    price: float
    signal_strength: float
    win_probability: float
    win_loss_ratio: float
    current_position_count: int
    current_gross_exposure: float
    daily_loss_breaker_triggered: bool
    drawdown_breached: bool
    regime_ok: bool = True
    connector_healthy: bool = True
    capital_allocation_ok: bool = True
    correlation_result: Optional[CorrelationCheckResult] = None
    strategy_id: str = ""


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    asset: str
    strategy_id: str
    timestamp: datetime
    checks: list[RiskCheckResult] = field(default_factory=list)
    quantity: float = 0.0
    position_sizing: Optional[PositionSizeResult] = None
    rationale: str = ""
    processing_time_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "asset": self.asset,
            "strategy_id": self.strategy_id,
            "timestamp": self.timestamp.isoformat(),
            "rationale": self.rationale,
            "quantity": self.quantity,
            "processing_time_ms": self.processing_time_ms,
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail} for c in self.checks
            ],
            "position_sizing": (
                {
                    "kelly_fraction_full": self.position_sizing.kelly_fraction_full,
                    "kelly_fraction_applied": self.position_sizing.kelly_fraction_applied,
                    "position_value": self.position_sizing.position_value,
                    "rejected": self.position_sizing.rejected,
                    "rejection_reason": self.position_sizing.rejection_reason,
                }
                if self.position_sizing
                else None
            ),
        }


def write_decision_audit(decision: RiskDecision, path: Optional[str] = None) -> None:
    """Appends a decision to the immutable, append-only audit trail
    (7-year retention per DOC 2 §8). Creates parent directories on demand."""
    target = path or decision_audit_path()
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "a", encoding="utf-8") as f:
        f.write(json.dumps(decision.to_dict()) + "\n")


class RiskManager:
    def __init__(
        self,
        config: RiskConfig,
        position_sizer: PositionSizer,
        safe_mode_manager: SafeModeManager,
    ) -> None:
        self.config = config
        self.position_sizer = position_sizer
        self.safe_mode = safe_mode_manager

    def check_pre_trade(self, ctx: PreTradeContext) -> RiskDecision:
        start_perf = time.perf_counter()
        checks: list[RiskCheckResult] = []
        sizing: Optional[PositionSizeResult] = None

        def record(name: str, passed: bool, detail: Optional[str] = None) -> bool:
            checks.append(RiskCheckResult(name=name, passed=passed, detail=detail))
            return passed

        def finalize(approved: bool, quantity: float = 0.0) -> RiskDecision:
            rationale = "approved" if approved else (checks[-1].detail or checks[-1].name)
            elapsed_ms = (time.perf_counter() - start_perf) * 1000
            decision = RiskDecision(
                approved=approved,
                asset=ctx.asset,
                strategy_id=ctx.strategy_id,
                timestamp=ctx.now,
                checks=checks,
                quantity=quantity,
                position_sizing=sizing,
                rationale=rationale,
                processing_time_ms=max(elapsed_ms, 0.0),
            )
            write_decision_audit(decision)
            return decision

        # 1. Strategy status
        ok = ctx.strategy_enabled and ctx.trading_mode_ok
        if not record("strategy_status", ok, None if ok else "strategy disabled or trading-mode mismatch"):
            return finalize(False)

        # 2. Safe mode (exits always allowed even during entry-block)
        entries_allowed = self.safe_mode.entries_allowed(ctx.now)
        ok = entries_allowed if ctx.is_entry else True
        if not record("safe_mode", ok, None if ok else "safe mode active, entries halted"):
            return finalize(False)

        # 3. Daily loss breaker
        ok = not ctx.daily_loss_breaker_triggered
        if not record("daily_loss_breaker", ok, None if ok else "daily loss breaker active"):
            return finalize(False)

        # 4. Drawdown ceiling
        ok = not ctx.drawdown_breached
        if not record("drawdown_ceiling", ok, None if ok else "drawdown ceiling breached"):
            return finalize(False)

        # 5. Position limit (entry only)
        if ctx.is_entry:
            ok = ctx.current_position_count < self.config.max_concurrent_positions
            detail = None if ok else f"max concurrent positions ({self.config.max_concurrent_positions}) reached"
            if not record("position_limit", ok, detail):
                return finalize(False)
        else:
            record("position_limit", True, "skipped (exit)")

        # 6. Correlation (entry only)
        if ctx.is_entry:
            corr = ctx.correlation_result
            ok = corr is None or not corr.exceeded
            detail = (
                None
                if ok
                else f"correlation {corr.max_correlation:.2f} with {corr.correlated_symbol} "
                f"exceeds cap {self.config.correlation_cap}"
            )
            if not record("correlation", ok, detail):
                return finalize(False)
        else:
            record("correlation", True, "skipped (exit)")

        # 7. Regime filter
        if not record("regime_filter", ctx.regime_ok, None if ctx.regime_ok else "regime filter blocks entry"):
            return finalize(False)

        # 8. Position sizing (Kelly)
        sizing = self.position_sizer.calculate_size(
            win_probability=ctx.win_probability,
            win_loss_ratio=ctx.win_loss_ratio,
            signal_strength=ctx.signal_strength,
            portfolio_value=ctx.portfolio_value,
            price=ctx.price,
            safe_mode_multiplier=self.safe_mode.size_multiplier(ctx.now),
        )
        if not record("position_sizing", not sizing.rejected, sizing.rejection_reason):
            return finalize(False)

        # 9. Gross exposure (entry only)
        if ctx.is_entry:
            new_exposure = ctx.current_gross_exposure + (sizing.position_value / ctx.portfolio_value)
            ok = new_exposure <= self.config.max_gross_exposure
            detail = (
                None
                if ok
                else f"gross exposure {new_exposure:.2%} exceeds cap {self.config.max_gross_exposure:.2%}"
            )
            if not record("gross_exposure", ok, detail):
                return finalize(False)
        else:
            record("gross_exposure", True, "skipped (exit)")

        # 10. Leverage (entry only)
        if ctx.is_entry:
            leverage = sizing.position_value / ctx.portfolio_value
            ok = leverage <= self.config.max_leverage
            detail = None if ok else f"leverage {leverage:.2f}x exceeds cap {self.config.max_leverage}x"
            if not record("leverage", ok, detail):
                return finalize(False)
        else:
            record("leverage", True, "skipped (exit)")

        # 11. Capital allocation (entry only)
        if ctx.is_entry:
            ok = ctx.capital_allocation_ok
            if not record("capital_allocation", ok, None if ok else "capital allocation limits exceeded"):
                return finalize(False)
        else:
            record("capital_allocation", True, "skipped (exit)")

        # 12. Minimum portfolio
        ok = ctx.portfolio_value >= self.config.min_portfolio_value
        detail = None if ok else f"portfolio value {ctx.portfolio_value} below minimum {self.config.min_portfolio_value}"
        if not record("minimum_portfolio", ok, detail):
            return finalize(False)

        # 13. Connector health -> ORDER PLACED
        if not record("connector_health", ctx.connector_healthy, None if ctx.connector_healthy else "connector unhealthy"):
            return finalize(False)

        return finalize(True, quantity=sizing.quantity)
