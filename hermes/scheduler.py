"""Lightweight cron-like scheduler (DOC 5 §1) — no external cron library.
Each job's due-ness is a pure predicate from hermes.schedules checked
against PersistentMemory's last-run tracking, so `run_due_jobs()` is fully
deterministic and testable with synthetic timestamps — the same pattern
used throughout this codebase for anything time-driven (BreakerManager,
SafeModeManager, HeartbeatWatchdog).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

import structlog

from hermes.memory import PersistentMemory
from hermes.schedules import SchedulePredicate

log = structlog.get_logger(service="hermes")

JobHandler = Callable[[datetime], Awaitable[None]]


@dataclass(frozen=True)
class CronJob:
    name: str
    schedule: SchedulePredicate
    handler: JobHandler


class CronScheduler:
    def __init__(self, memory: PersistentMemory, jobs: list[CronJob]) -> None:
        self.memory = memory
        self.jobs = jobs

    async def run_due_jobs(self, now: Optional[datetime] = None) -> list[str]:
        """Runs every job whose schedule predicate says it's due, updates its
        last-run timestamp on success, and returns the names of jobs that ran
        this call. One job's failure is logged and does not stop the others
        from running in the same tick."""
        now = now or datetime.now(timezone.utc)
        ran: list[str] = []

        for job in self.jobs:
            last_run = await self.memory.get_last_run(job.name)
            if not job.schedule(now, last_run):
                continue
            try:
                await job.handler(now)
                await self.memory.set_last_run(job.name, now)
                ran.append(job.name)
            except Exception:
                log.exception("hermes_job_failed", job=job.name)

        return ran
