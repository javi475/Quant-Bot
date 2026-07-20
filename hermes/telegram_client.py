"""Lightweight Telegram Bot API client for polling incoming commands (DOC 5
§5-6). common.telegram.TelegramAlertService already covers outbound alerts;
this adds only the getUpdates long-poll Hermes needs to receive operator
commands — not the full python-telegram-bot Application/Updater machinery,
which runs its own event loop and would fight with ours.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

TELEGRAM_API_BASE = "https://api.telegram.org"
DEFAULT_POLL_TIMEOUT_SECONDS = 30


class TelegramUpdatesClient:
    def __init__(
        self, bot_token: str, http_client: httpx.AsyncClient, poll_timeout_seconds: int = DEFAULT_POLL_TIMEOUT_SECONDS
    ) -> None:
        self.bot_token = bot_token
        self.http = http_client
        self.poll_timeout_seconds = poll_timeout_seconds
        self._offset: Optional[int] = None

    async def get_updates(self) -> list[dict[str, Any]]:
        """Long-polls for updates since the last call, advancing the internal
        offset so each update is only ever returned once."""
        params: dict[str, Any] = {"timeout": self.poll_timeout_seconds}
        if self._offset is not None:
            params["offset"] = self._offset

        response = await self.http.get(f"{TELEGRAM_API_BASE}/bot{self.bot_token}/getUpdates", params=params)
        response.raise_for_status()
        updates = response.json().get("result", [])
        if updates:
            self._offset = updates[-1]["update_id"] + 1
        return updates

    async def send_message(self, chat_id: str, text: str) -> None:
        response = await self.http.post(
            f"{TELEGRAM_API_BASE}/bot{self.bot_token}/sendMessage", json={"chat_id": chat_id, "text": text}
        )
        response.raise_for_status()
