"""Post-breaker protocol state machine (DOC 4 §3.4, §7): INACTIVE ->
ENTRY_BLOCK (48h) -> RECOVERY (7 days graduated 50/75/100%) -> INACTIVE.

Daily loss breaker allows new entries during ENTRY_BLOCK at post_breaker_size_mult
(0.5x); drawdown ceiling and dead-man switch halt entries entirely and require
an explicit manual_restart() before recovery can begin. A re-trigger while
already in RECOVERY escalates to a full halt + manual restart regardless of
what caused it (DOC 4 §3.4).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from engine.risk.risk_config import RiskConfig


class SafeModePhase(str, Enum):
    INACTIVE = "inactive"
    ENTRY_BLOCK = "entry_block"
    RECOVERY = "recovery"


class SafeModeManager:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config
        self.phase: SafeModePhase = SafeModePhase.INACTIVE
        self.triggered_by: Optional[str] = None
        self.halt_new_entries: bool = False
        self.requires_manual_restart: bool = False
        self._phase_started_at: Optional[datetime] = None

    @property
    def is_active(self) -> bool:
        return self.phase != SafeModePhase.INACTIVE

    def activate(
        self, triggered_by: str, halt_new_entries: bool, requires_manual_restart: bool, now: datetime
    ) -> None:
        self._advance(now)
        if self.phase == SafeModePhase.RECOVERY:
            # Any re-trigger mid-recovery escalates to a full halt (DOC 4 §3.4).
            halt_new_entries = True
            requires_manual_restart = True

        self.phase = SafeModePhase.ENTRY_BLOCK
        self.triggered_by = triggered_by
        self.halt_new_entries = halt_new_entries
        self.requires_manual_restart = requires_manual_restart
        self._phase_started_at = now

    def manual_restart(self, now: datetime) -> None:
        if self.phase != SafeModePhase.ENTRY_BLOCK:
            raise ValueError("manual_restart is only valid during the entry-block phase")
        self.requires_manual_restart = False
        self.halt_new_entries = False
        self.phase = SafeModePhase.RECOVERY
        self._phase_started_at = now

    def _advance(self, now: datetime) -> None:
        """Auto-advances ENTRY_BLOCK -> RECOVERY -> INACTIVE based on elapsed
        time, skipping the auto-advance out of ENTRY_BLOCK if a manual restart
        is required."""
        if self.phase == SafeModePhase.ENTRY_BLOCK:
            block_duration = timedelta(hours=self.config.post_breaker_duration_hours)
            elapsed = now - self._phase_started_at
            if elapsed >= block_duration and not self.requires_manual_restart:
                self.phase = SafeModePhase.RECOVERY
                self.halt_new_entries = False
                # Anchor recovery at when the block actually ended, not `now` —
                # otherwise a single _advance() call that jumps far past the
                # block can't also detect the recovery window has elapsed.
                self._phase_started_at = self._phase_started_at + block_duration

        if self.phase == SafeModePhase.RECOVERY:
            elapsed_days = (now - self._phase_started_at).total_seconds() / 86400
            if elapsed_days >= self.config.recovery_phase_3_days:
                self.phase = SafeModePhase.INACTIVE
                self.triggered_by = None
                self.halt_new_entries = False
                self.requires_manual_restart = False
                self._phase_started_at = None

    def size_multiplier(self, now: datetime) -> float:
        self._advance(now)

        if self.phase == SafeModePhase.INACTIVE:
            return 1.0

        if self.phase == SafeModePhase.ENTRY_BLOCK:
            return 0.0 if self.halt_new_entries else self.config.post_breaker_size_mult

        elapsed_days = (now - self._phase_started_at).total_seconds() / 86400
        if elapsed_days < self.config.recovery_phase_1_days:
            return 0.50
        if elapsed_days < self.config.recovery_phase_2_days:
            return 0.75
        return 1.0

    def entries_allowed(self, now: datetime) -> bool:
        return self.size_multiplier(now) > 0.0
