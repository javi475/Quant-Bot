"""In-trade risk monitoring (DOC 4 §10): per-cycle unrealized P&L checks,
gross exposure computation, and the risk-state snapshot broadcast to the
dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from engine.models.position import Position
from engine.risk.safe_mode import SafeModePhase


def check_max_loss_exit(position: Position, portfolio_value: float, max_risk_per_trade: float) -> bool:
    """True if this position's unrealized loss has reached the per-trade risk
    cap and should be force market-exited (DOC 4 §10)."""
    if portfolio_value <= 0 or position.unrealized_pnl >= 0:
        return False
    loss_pct = -position.unrealized_pnl / portfolio_value
    return loss_pct >= max_risk_per_trade


def compute_gross_exposure(positions: list[Position], portfolio_value: float) -> float:
    if portfolio_value <= 0:
        return 0.0
    return sum(abs(p.market_value) for p in positions) / portfolio_value


@dataclass(frozen=True)
class RiskStateSnapshot:
    timestamp: datetime
    equity: float
    daily_pnl_pct: float
    drawdown_pct: float
    gross_exposure_pct: float
    open_position_count: int
    safe_mode_active: bool
    safe_mode_phase: SafeModePhase

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "equity": self.equity,
            "daily_pnl_pct": self.daily_pnl_pct,
            "drawdown_pct": self.drawdown_pct,
            "gross_exposure_pct": self.gross_exposure_pct,
            "open_position_count": self.open_position_count,
            "safe_mode_active": self.safe_mode_active,
            "safe_mode_phase": self.safe_mode_phase.value,
        }
