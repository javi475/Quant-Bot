"""Orchestration jobs matching the DOC 5 §1 cron schedule. Every job in that
table is registered here (build_default_jobs), but several genuinely aren't
implemented this session — they log why via structlog rather than send
misleading Telegram alerts or silently pretend to do something. See each
stub's docstring for the specific missing dependency.

Real jobs: health_check, position_reconciliation, safe_mode_check,
daily_report, midday_status.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

import structlog

from hermes.client import HermesClient
from hermes.memory import PersistentMemory
from hermes.scheduler import CronJob
from hermes.schedules import daily_at, every_n_minutes, hourly_at, monthly_at, weekly_at

log = structlog.get_logger(service="hermes")

LAST_EQUITY_SNAPSHOT_KEY = "hermes:last_equity_snapshot"
EQUITY_SWING_WARNING_THRESHOLD = 0.05
EQUITY_SWING_SERIOUS_THRESHOLD = 0.10


class AlertSink(Protocol):
    async def send(self, message: str, priority: str = "critical") -> None: ...


# ----- Real jobs -----


async def health_check(now: datetime, client: HermesClient, memory: PersistentMemory, alert_sink: AlertSink) -> None:
    status = await client.status()
    equity = status.get("equity", 0.0)
    halted = bool(status.get("halted"))
    safe_mode = status.get("safe_mode", {})

    await memory.record_system_metrics(
        {
            "timestamp": now.isoformat(),
            "equity": equity,
            "halted": halted,
            "safe_mode_active": bool(safe_mode.get("active")),
        }
    )

    if halted:
        await alert_sink.send(f"Engine reports HALTED at health check. Equity: ${equity:,.2f}", priority="warning")


async def position_reconciliation(
    now: datetime, client: HermesClient, memory: PersistentMemory, alert_sink: AlertSink
) -> None:
    positions = await client.positions()
    equity = positions.get("equity", 0.0)

    previous = await memory.get_json(LAST_EQUITY_SNAPSHOT_KEY)
    await memory.set_json(LAST_EQUITY_SNAPSHOT_KEY, {"equity": equity, "timestamp": now.isoformat()})

    if previous and previous.get("equity"):
        change = (equity - previous["equity"]) / previous["equity"]
        if abs(change) >= EQUITY_SWING_WARNING_THRESHOLD:
            priority = "serious" if abs(change) >= EQUITY_SWING_SERIOUS_THRESHOLD else "warning"
            await alert_sink.send(
                f"Equity moved {change:+.1%} since last reconciliation "
                f"(${previous['equity']:,.2f} -> ${equity:,.2f}).",
                priority=priority,
            )


async def safe_mode_check(now: datetime, client: HermesClient, memory: PersistentMemory, alert_sink: AlertSink) -> None:
    status = await client.status()
    safe_mode = status.get("safe_mode", {})

    if not safe_mode.get("active"):
        await memory.clear_safe_mode_alert()
        return

    triggered_by = safe_mode.get("triggered_by") or "unknown"
    phase = safe_mode.get("phase") or "unknown"
    if await memory.has_alerted_safe_mode(triggered_by, phase):
        return  # already alerted on this exact episode — don't spam every 15 min

    await memory.mark_safe_mode_alerted(triggered_by, phase)
    restart_note = " Requires manual restart." if safe_mode.get("requires_manual_restart") else ""
    await alert_sink.send(
        f"Safe mode active — phase: {phase}, triggered by: {triggered_by}.{restart_note}", priority="serious"
    )


async def daily_report(now: datetime, client: HermesClient, memory: PersistentMemory, alert_sink: AlertSink) -> None:
    status = await client.status()
    trades_result = await client.trades()
    trades = trades_result.get("trades", [])
    closed = [t for t in trades if t.get("is_closed")]
    total_pnl = sum(t.get("pnl") or 0.0 for t in closed)
    safe_mode = status.get("safe_mode", {})

    message = (
        f"Daily report ({now.date().isoformat()})\n"
        f"Equity: ${status.get('equity', 0.0):,.2f}\n"
        f"Open positions: {status.get('open_position_count', 0)}\n"
        f"Closed trades: {len(closed)}, total P&L ${total_pnl:,.2f}\n"
        f"Safe mode: {'ACTIVE (' + safe_mode.get('phase', '') + ')' if safe_mode.get('active') else 'inactive'}\n"
        f"Engine: {'HALTED' if status.get('halted') else 'running'}"
    )
    await alert_sink.send(message, priority="info")


async def midday_status(now: datetime, client: HermesClient, memory: PersistentMemory, alert_sink: AlertSink) -> None:
    status = await client.status()
    safe_mode = status.get("safe_mode", {})
    await alert_sink.send(
        f"Midday status — Equity: ${status.get('equity', 0.0):,.2f}, "
        f"Open positions: {status.get('open_position_count', 0)}, "
        f"Safe mode: {'ACTIVE' if safe_mode.get('active') else 'inactive'}",
        priority="info",
    )


# ----- Honest stubs: registered on the schedule, not yet implemented -----


async def _log_not_implemented(job_name: str, reason: str) -> None:
    log.info("hermes_job_not_implemented", job=job_name, reason=reason)


async def weekly_backtest(now: datetime, client: HermesClient, memory: PersistentMemory, alert_sink: AlertSink) -> None:
    await _log_not_implemented(
        "weekly_backtest",
        "requires a wired historical data source — the M3 backtester exists but isn't connected to a live "
        "market-data feed or a per-strategy scheduling policy yet",
    )


async def self_improvement_proposal(
    now: datetime, client: HermesClient, memory: PersistentMemory, alert_sink: AlertSink
) -> None:
    await _log_not_implemented(
        "self_improvement_proposal", "parameter re-optimization + proposal generation/approval workflow isn't built"
    )


async def phase_gate_check(now: datetime, client: HermesClient, memory: PersistentMemory, alert_sink: AlertSink) -> None:
    await _log_not_implemented(
        "phase_gate_check", "launch-phase tracking (paper/small/half/full, DOC 1 §7) isn't persisted anywhere yet"
    )


async def monthly_report(now: datetime, client: HermesClient, memory: PersistentMemory, alert_sink: AlertSink) -> None:
    await _log_not_implemented(
        "monthly_report", "would aggregate the same data daily_report already pulls — monthly rollup isn't built"
    )


async def log_rotation_check(
    now: datetime, client: HermesClient, memory: PersistentMemory, alert_sink: AlertSink
) -> None:
    await _log_not_implemented(
        "log_rotation_check", "log file management belongs to the VPS deployment milestone (DOC 6), not yet built"
    )


async def daily_pnl_reset(now: datetime, client: HermesClient, memory: PersistentMemory, alert_sink: AlertSink) -> None:
    await _log_not_implemented(
        "daily_pnl_reset",
        "the Engine's BreakerManager already resets its own daily P&L window automatically at UTC midnight "
        "(DOC 4 §2) — this job is meant to be a verification step, but no verification logic is built yet",
    )


async def weekly_backup_verify(
    now: datetime, client: HermesClient, memory: PersistentMemory, alert_sink: AlertSink
) -> None:
    await _log_not_implemented(
        "weekly_backup_verify", "backup/restore tooling is part of the VPS deployment milestone (DOC 6 §8)"
    )


def build_default_jobs(client: HermesClient, memory: PersistentMemory, alert_sink: AlertSink) -> list[CronJob]:
    """Wires every DOC 5 §1 cron entry to its handler (real or stub) and
    schedule predicate. Cron weekday 1=Monday/0=Sunday is translated to
    Python's datetime.weekday() convention (Monday=0 ... Sunday=6)."""

    def bind(handler):
        return lambda now: handler(now, client, memory, alert_sink)

    return [
        CronJob("health_check", every_n_minutes(5), bind(health_check)),
        CronJob("daily_report", daily_at(8, 0), bind(daily_report)),
        CronJob("weekly_backtest", weekly_at(0, 0, 0), bind(weekly_backtest)),
        CronJob("self_improvement_proposal", weekly_at(0, 2, 0), bind(self_improvement_proposal)),
        CronJob("phase_gate_check", weekly_at(0, 4, 0), bind(phase_gate_check)),
        CronJob("monthly_report", monthly_at(1, 6, 0), bind(monthly_report)),
        CronJob("position_reconciliation", every_n_minutes(30), bind(position_reconciliation)),
        CronJob("log_rotation_check", hourly_at(0), bind(log_rotation_check)),
        CronJob("daily_pnl_reset", daily_at(0, 0), bind(daily_pnl_reset)),
        CronJob("midday_status", daily_at(12, 0), bind(midday_status)),
        CronJob("weekly_backup_verify", weekly_at(6, 0, 0), bind(weekly_backup_verify)),
        CronJob("safe_mode_check", every_n_minutes(15), bind(safe_mode_check)),
    ]
