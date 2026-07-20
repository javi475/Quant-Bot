"""Telegram command handling (DOC 5 §5-6): /status /positions /risk
/risk_set /halt /flatten /kill /confirm /cancel /help. Destructive commands
(halt/flatten/kill/risk_set) require a second /confirm within 60 seconds
(DOC 5 §6) — armed in memory on this handler instance rather than persisted,
since losing an unconfirmed action to a restart is the safe failure mode.

Only the DOC 5 §5 commands with real backend support are implemented.
Everything else in DOC 5's command table (/backtest /paper /live /proposal
/approve /reject /phase /backup /logs /report /restart /connectors
/strategies) replies with what's actually missing instead of silently doing
nothing — see _UNSUPPORTED_COMMANDS.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

import structlog

from hermes.client import HermesClient, HermesClientError

log = structlog.get_logger(service="hermes")

CONFIRMATION_WINDOW_SECONDS = 60
DESTRUCTIVE_COMMANDS = {"halt", "flatten", "kill", "risk_set"}

_UNSUPPORTED_COMMANDS = {
    "backtest": "scheduling a backtest from Telegram isn't built — use the dashboard's Backtesting page",
    "paper": "paper deployment via Telegram isn't built — use the dashboard's Deployment page",
    "live": "live deployment via Telegram isn't built — use the dashboard's Deployment page",
    "restart": "there's no separate 'restart' concept — safe-mode recovery is automatic per DOC 4 §7",
    "proposal": "the self-improvement proposal workflow isn't built yet",
    "approve": "the self-improvement proposal workflow isn't built yet",
    "reject": "the self-improvement proposal workflow isn't built yet",
    "phase": "launch-phase tracking isn't persisted yet",
    "backup": "backup tooling is part of the VPS deployment milestone (DOC 6 §8)",
    "logs": "log access via Telegram isn't built — check the VPS directly once deployed",
    "report": "use /status for now — the full report format is what daily_report sends automatically",
    "connectors": "use the dashboard's Connectors page",
    "strategies": "use the dashboard's Strategies page",
    "start": "use /help to see available commands",
}

HELP_TEXT = (
    "Available commands:\n"
    "/status — Engine equity, positions, safe mode, halted state\n"
    "/positions — open position count and gross exposure\n"
    "/risk — current risk parameters\n"
    "/risk_set <param> <value> — update one risk parameter (requires /confirm)\n"
    "/halt — stop new entries (requires /confirm)\n"
    "/flatten — close every open position (requires /confirm)\n"
    "/kill — flatten + disable all strategies + halt (requires /confirm)\n"
    "/confirm — confirm a pending destructive action within 60s\n"
    "/cancel — cancel a pending destructive action\n"
    "/help — this message"
)

ReplySender = Callable[[str], Awaitable[None]]


@dataclass
class PendingConfirmation:
    command: str
    args: list[str]
    created_at: datetime

    def is_expired(self, now: datetime) -> bool:
        return (now - self.created_at).total_seconds() > CONFIRMATION_WINDOW_SECONDS


class TelegramCommandHandler:
    def __init__(self, client: HermesClient, authorized_chat_id: str) -> None:
        self.client = client
        self.authorized_chat_id = str(authorized_chat_id)
        self._pending: Optional[PendingConfirmation] = None

    async def handle_update(self, update: dict[str, Any], reply: ReplySender, now: Optional[datetime] = None) -> None:
        now = now or datetime.now(timezone.utc)
        message = update.get("message") or {}
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = (message.get("text") or "").strip()

        if not text.startswith("/"):
            return
        if chat_id != self.authorized_chat_id:
            log.warning("hermes_unauthorized_telegram_sender", chat_id=chat_id)
            return

        parts = text[1:].split()
        if not parts:
            return
        command, args = parts[0].lower(), parts[1:]
        await self._dispatch(command, args, reply, now)

    async def _dispatch(self, command: str, args: list[str], reply: ReplySender, now: datetime) -> None:
        if command == "confirm":
            await self._handle_confirm(reply, now)
            return
        if command == "cancel":
            if self._pending is not None:
                self._pending = None
                await reply("Cancelled.")
            else:
                await reply("Nothing pending to cancel.")
            return
        if command == "help":
            await reply(HELP_TEXT)
            return
        if command in _UNSUPPORTED_COMMANDS:
            await reply(f"Not available yet: {_UNSUPPORTED_COMMANDS[command]}")
            return

        if command in DESTRUCTIVE_COMMANDS:
            self._pending = PendingConfirmation(command=command, args=args, created_at=now)
            await reply(f"⚠️ /{command} requires confirmation. Send /confirm within 60s to proceed, or /cancel.")
            return

        if command == "status":
            await self._reply_status(reply)
        elif command == "positions":
            await self._reply_positions(reply)
        elif command == "risk":
            await self._reply_risk(reply)
        else:
            await reply(f"Unknown command: /{command}. Send /help for the list of available commands.")

    async def _handle_confirm(self, reply: ReplySender, now: datetime) -> None:
        if self._pending is None:
            await reply("Nothing pending to confirm.")
            return
        if self._pending.is_expired(now):
            self._pending = None
            await reply("Confirmation window expired — re-issue the command.")
            return

        pending = self._pending
        self._pending = None
        await self._execute(pending, reply)

    async def _execute(self, pending: PendingConfirmation, reply: ReplySender) -> None:
        try:
            if pending.command == "halt":
                await self.client.halt()
                await reply("Halted.")
            elif pending.command == "flatten":
                await self.client.flatten()
                await reply("Flattened.")
            elif pending.command == "kill":
                await self.client.kill()
                await reply("Kill switch activated.")
            elif pending.command == "risk_set":
                if len(pending.args) != 2:
                    await reply("Usage: /risk_set <param> <value>")
                    return
                param, raw_value = pending.args
                try:
                    value: Any = float(raw_value)
                except ValueError:
                    await reply(f"'{raw_value}' isn't a valid number.")
                    return
                result = await self.client.risk_set({param: value})
                await reply(f"{param} updated to {result.get(param, value)}.")
        except HermesClientError as exc:
            await reply(f"Failed: {exc}")

    async def _reply_status(self, reply: ReplySender) -> None:
        try:
            status = await self.client.status()
        except HermesClientError as exc:
            await reply(f"Could not reach the Engine: {exc}")
            return
        safe_mode = status.get("safe_mode", {})
        phase_note = f" ({safe_mode.get('phase')})" if safe_mode.get("active") else ""
        await reply(
            f"Equity: ${status.get('equity', 0.0):,.2f}\n"
            f"Open positions: {status.get('open_position_count', 0)}\n"
            f"Safe mode: {'ACTIVE' + phase_note if safe_mode.get('active') else 'inactive'}\n"
            f"Engine: {'HALTED' if status.get('halted') else 'running'}"
        )

    async def _reply_positions(self, reply: ReplySender) -> None:
        try:
            positions = await self.client.positions()
        except HermesClientError as exc:
            await reply(f"Could not reach the Engine: {exc}")
            return
        await reply(
            f"Open positions: {positions.get('open_position_count', 0)}\n"
            f"Gross exposure: ${positions.get('gross_exposure_value', 0.0):,.2f}"
        )

    async def _reply_risk(self, reply: ReplySender) -> None:
        try:
            params = await self.client.risk_get()
        except HermesClientError as exc:
            await reply(f"Could not reach the Engine: {exc}")
            return
        lines = [f"{k}: {v}" for k, v in sorted(params.items())]
        await reply("Current risk parameters:\n" + "\n".join(lines))
