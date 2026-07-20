"""Telegram alerting (DOC 5 §10): priority levels, message formatting, and a
minimum-priority filter (TELEGRAM_ALERT_PRIORITY) — critical alerts always
send regardless of that filter. Implements the same `AlertSink` protocol the
watchdog expects (`async def send(message, priority="critical")`), so it can
be passed directly in place of `watchdog.heartbeat_watchdog.LoggingAlertSink`
once a bot token/chat id are configured.
"""

from __future__ import annotations

import httpx

PRIORITY_ORDER = ("info", "warning", "serious", "critical")
PRIORITY_EMOJI = {"info": "ℹ️", "warning": "⚠️", "serious": "\U0001f536", "critical": "\U0001f6a8"}

SEPARATOR = "—" * 28  # em-dash rule, per DOC 5 §10 formatting
MAX_MESSAGE_LENGTH = 4096
TELEGRAM_API_BASE = "https://api.telegram.org"


def format_alert(message: str, priority: str) -> str:
    emoji = PRIORITY_EMOJI.get(priority, "")
    title = priority.upper()
    text = f"{emoji} {title}\n{SEPARATOR}\n{message}"
    return text[:MAX_MESSAGE_LENGTH]


def _priority_rank(priority: str) -> int:
    return PRIORITY_ORDER.index(priority) if priority in PRIORITY_ORDER else 0


class TelegramAlertService:
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        http_client: httpx.AsyncClient,
        min_priority: str = "info",
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.http = http_client
        self.min_priority = min_priority

    async def send(self, message: str, priority: str = "critical") -> bool:
        """Returns whether the message was actually sent (False if filtered
        out by min_priority — critical alerts are never filtered)."""
        if priority != "critical" and _priority_rank(priority) < _priority_rank(self.min_priority):
            return False

        url = f"{TELEGRAM_API_BASE}/bot{self.bot_token}/sendMessage"
        response = await self.http.post(url, json={"chat_id": self.chat_id, "text": format_alert(message, priority)})
        response.raise_for_status()
        return True
