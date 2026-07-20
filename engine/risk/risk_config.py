"""Complete risk parameter table (DOC 4 §8). Loaded from system_settings at
Engine startup; changes apply immediately to the running Engine, but risk
parameters themselves are human-controlled only (DOC 4 open questions —
Hermes may propose strategy parameter changes, never risk parameters)."""

from __future__ import annotations

from dataclasses import dataclass, fields


class RiskConfigError(ValueError):
    pass


@dataclass
class RiskConfig:
    kelly_multiplier: float = 0.25
    max_risk_per_trade: float = 0.02
    daily_loss_breaker: float = -0.03
    max_drawdown: float = 0.15
    max_concurrent_positions: int = 3
    max_gross_exposure: float = 0.60
    correlation_cap: float = 0.70
    heartbeat_timeout_seconds: int = 300
    post_breaker_size_mult: float = 0.50
    post_breaker_duration_hours: int = 48
    max_leverage: float = 2.0
    correlation_lookback_days: int = 30
    drawdown_alert_1: float = 0.08
    drawdown_alert_2: float = 0.10
    drawdown_alert_3: float = 0.12
    recovery_phase_1_days: int = 2
    recovery_phase_2_days: int = 4
    recovery_phase_3_days: int = 7
    heartbeat_interval_seconds: int = 5
    watchdog_check_interval_seconds: int = 5
    min_portfolio_value: float = 1000.0
    per_strategy_min_allocation: float = 0.10
    per_strategy_max_allocation: float = 0.40
    cash_reserve_min: float = 0.20

    # (field name) -> (min, max) inclusive, per the DOC 4 §8 parameter table.
    RANGES = {
        "kelly_multiplier": (0.10, 0.50),
        "max_risk_per_trade": (0.005, 0.03),
        "daily_loss_breaker": (-0.05, -0.01),
        "max_drawdown": (0.10, 0.20),
        "max_concurrent_positions": (1, 10),
        "max_gross_exposure": (0.30, 0.80),
        "correlation_cap": (0.50, 0.90),
        "heartbeat_timeout_seconds": (60, 900),
        "post_breaker_size_mult": (0.25, 0.75),
        "post_breaker_duration_hours": (24, 96),
        "max_leverage": (1.0, 2.0),
        "correlation_lookback_days": (7, 90),
        "heartbeat_interval_seconds": (1, 15),
        "watchdog_check_interval_seconds": (1, 30),
        "min_portfolio_value": (100.0, 10000.0),
        "per_strategy_min_allocation": (0.05, 0.25),
        "per_strategy_max_allocation": (0.20, 0.60),
        "cash_reserve_min": (0.10, 0.50),
    }

    def validate(self) -> None:
        violations: list[str] = []

        for name, (lo, hi) in self.RANGES.items():
            value = getattr(self, name)
            if not (lo <= value <= hi):
                violations.append(f"{name}={value} outside range [{lo}, {hi}]")

        if self.per_strategy_min_allocation > self.per_strategy_max_allocation:
            violations.append(
                "per_strategy_min_allocation must be <= per_strategy_max_allocation "
                f"({self.per_strategy_min_allocation} > {self.per_strategy_max_allocation})"
            )

        if not (self.drawdown_alert_1 < self.drawdown_alert_2 < self.drawdown_alert_3 < self.max_drawdown):
            violations.append(
                "drawdown alert levels must satisfy alert_1 < alert_2 < alert_3 < max_drawdown "
                f"({self.drawdown_alert_1} < {self.drawdown_alert_2} < "
                f"{self.drawdown_alert_3} < {self.max_drawdown})"
            )

        if not (self.recovery_phase_1_days < self.recovery_phase_2_days < self.recovery_phase_3_days):
            violations.append(
                "recovery phase days must satisfy phase_1 < phase_2 < phase_3 "
                f"({self.recovery_phase_1_days} < {self.recovery_phase_2_days} < "
                f"{self.recovery_phase_3_days})"
            )

        if violations:
            raise RiskConfigError("; ".join(violations))

    @classmethod
    def from_dict(cls, data: dict) -> "RiskConfig":
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        config = cls(**filtered)
        config.validate()
        return config
