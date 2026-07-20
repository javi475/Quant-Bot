"""Daily loss breaker and drawdown ceiling (DOC 4 §2-3). Both are stateful,
time-driven checks: the caller feeds in the latest P&L/equity each engine
cycle and reads back whether a breaker has tripped or an alert level has
newly escalated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from engine.risk.risk_config import RiskConfig


@dataclass(frozen=True)
class DailyLossBreakerResult:
    triggered: bool
    daily_pnl_pct: float
    newly_triggered: bool  # True only on the cycle the breaker first trips


@dataclass(frozen=True)
class DrawdownCheckResult:
    current_drawdown: float
    peak_equity: float
    breached: bool
    alert_level: Optional[str]  # "info" | "warning" | "serious" | "breach" | None
    newly_escalated: bool  # True only when alert_level is a new high-water mark


class BreakerManager:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config
        self._daily_reset_date = None
        self._daily_triggered_today = False
        self._peak_equity: Optional[float] = None
        self._max_alert_reached_this_episode: Optional[str] = None

    _ALERT_ORDER = ["info", "warning", "serious", "breach"]

    def check_daily_loss(self, realized_pnl: float, unrealized_pnl: float, nav: float, now: datetime) -> DailyLossBreakerResult:
        today = now.date()
        if self._daily_reset_date != today:
            self._daily_reset_date = today
            self._daily_triggered_today = False

        pct = (realized_pnl + unrealized_pnl) / nav if nav else 0.0
        triggered = pct <= self.config.daily_loss_breaker
        newly_triggered = triggered and not self._daily_triggered_today
        if triggered:
            self._daily_triggered_today = True

        return DailyLossBreakerResult(
            triggered=triggered, daily_pnl_pct=pct, newly_triggered=newly_triggered
        )

    def check_drawdown(self, equity: float) -> DrawdownCheckResult:
        if self._peak_equity is None or equity > self._peak_equity:
            self._peak_equity = equity

        drawdown = 0.0 if not self._peak_equity else (self._peak_equity - equity) / self._peak_equity
        breached = drawdown >= self.config.max_drawdown
        level = self._alert_level_for(drawdown)

        newly_escalated = False
        if level is None:
            # Recovered below the lowest alert threshold: reset the episode so
            # a future re-crossing raises alerts again.
            self._max_alert_reached_this_episode = None
        else:
            current_rank = self._ALERT_ORDER.index(level)
            prior_rank = (
                self._ALERT_ORDER.index(self._max_alert_reached_this_episode)
                if self._max_alert_reached_this_episode
                else -1
            )
            if current_rank > prior_rank:
                newly_escalated = True
                self._max_alert_reached_this_episode = level

        return DrawdownCheckResult(
            current_drawdown=drawdown,
            peak_equity=self._peak_equity,
            breached=breached,
            alert_level=level,
            newly_escalated=newly_escalated,
        )

    def _alert_level_for(self, drawdown: float) -> Optional[str]:
        if drawdown >= self.config.max_drawdown:
            return "breach"
        if drawdown >= self.config.drawdown_alert_3:
            return "serious"
        if drawdown >= self.config.drawdown_alert_2:
            return "warning"
        if drawdown >= self.config.drawdown_alert_1:
            return "info"
        return None
