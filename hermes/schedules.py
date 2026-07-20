"""Cron-like schedule predicates (DOC 5 §1) as pure functions of
`(now, last_run) -> bool`, rather than a cron-expression parser. Each
predicate is a closure that keeps this deterministic and trivially testable
with synthetic timestamps.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

SchedulePredicate = Callable[[datetime, Optional[datetime]], bool]


def every_n_minutes(n: int) -> SchedulePredicate:
    def predicate(now: datetime, last_run: Optional[datetime]) -> bool:
        if last_run is None:
            return True
        return (now - last_run).total_seconds() >= n * 60

    return predicate


def hourly_at(minute: int = 0) -> SchedulePredicate:
    def predicate(now: datetime, last_run: Optional[datetime]) -> bool:
        if now.minute != minute:
            return False
        if last_run is None:
            return True
        last_marker = last_run.replace(minute=0, second=0, microsecond=0)
        now_marker = now.replace(minute=0, second=0, microsecond=0)
        return last_marker != now_marker

    return predicate


def daily_at(hour: int, minute: int = 0) -> SchedulePredicate:
    def predicate(now: datetime, last_run: Optional[datetime]) -> bool:
        if now.hour != hour or now.minute != minute:
            return False
        if last_run is None:
            return True
        return last_run.date() != now.date()

    return predicate


def weekly_at(weekday: int, hour: int, minute: int = 0) -> SchedulePredicate:
    """`weekday` follows Python's convention: Monday=0 ... Sunday=6."""

    def predicate(now: datetime, last_run: Optional[datetime]) -> bool:
        if now.weekday() != weekday or now.hour != hour or now.minute != minute:
            return False
        if last_run is None:
            return True
        return last_run.date() != now.date()

    return predicate


def monthly_at(day: int, hour: int, minute: int = 0) -> SchedulePredicate:
    def predicate(now: datetime, last_run: Optional[datetime]) -> bool:
        if now.day != day or now.hour != hour or now.minute != minute:
            return False
        if last_run is None:
            return True
        return (last_run.year, last_run.month) != (now.year, now.month)

    return predicate
