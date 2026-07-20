"""Hermes orchestrator entrypoint (DOC 5): wires HermesClient +
PersistentMemory + CronScheduler + TelegramCommandHandler into one process.
`tick()` is the single testable unit of work (checks due cron jobs, drains
pending Telegram updates); `run_forever()` just calls it in a loop — the
same convention as AlgorithmEngine.run_cycle()/run() and
HeartbeatWatchdog.check_once()/run_forever().
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import structlog

from hermes.client import HermesClient
from hermes.commands import TelegramCommandHandler
from hermes.jobs import AlertSink, build_default_jobs
from hermes.memory import PersistentMemory
from hermes.scheduler import CronScheduler
from hermes.telegram_client import TelegramUpdatesClient

log = structlog.get_logger(service="hermes")

DEFAULT_TICK_INTERVAL_SECONDS = 30


class HermesApp:
    def __init__(
        self,
        client: HermesClient,
        memory: PersistentMemory,
        alert_sink: AlertSink,
        command_handler: Optional[TelegramCommandHandler] = None,
        updates_client: Optional[TelegramUpdatesClient] = None,
    ) -> None:
        self.client = client
        self.memory = memory
        self.alert_sink = alert_sink
        self.scheduler = CronScheduler(memory, build_default_jobs(client, memory, alert_sink))
        self.command_handler = command_handler
        self.updates_client = updates_client
        self._running = False

    async def tick(self, now: Optional[datetime] = None) -> list[str]:
        """Runs whatever cron jobs are due and drains any pending Telegram
        commands. Returns the names of jobs that ran, for tests/logging."""
        now = now or datetime.now(timezone.utc)
        ran = await self.scheduler.run_due_jobs(now)

        if self.command_handler is not None and self.updates_client is not None:
            updates = await self.updates_client.get_updates()
            for update in updates:
                await self._handle_update(update, now)

        return ran

    async def _handle_update(self, update: dict, now: datetime) -> None:
        chat_id = str(update.get("message", {}).get("chat", {}).get("id", ""))

        async def reply(text: str) -> None:
            await self.updates_client.send_message(chat_id, text)

        await self.command_handler.handle_update(update, reply, now)

    async def run_forever(self, tick_interval_seconds: float = DEFAULT_TICK_INTERVAL_SECONDS) -> None:
        self._running = True
        while self._running:
            try:
                await self.tick()
            except Exception:
                log.exception("hermes_tick_failed")
            await asyncio.sleep(tick_interval_seconds)

    def stop(self) -> None:
        self._running = False


if __name__ == "__main__":  # pragma: no cover - deployment entrypoint
    import os

    async def main() -> None:
        import httpx
        import redis.asyncio as redis_asyncio

        from common.telegram import TelegramAlertService

        dashboard_url = os.environ["DASHBOARD_API_URL"]
        hmac_secret = os.environ["HERMES_HMAC_SECRET"]
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        min_priority = os.environ.get("TELEGRAM_ALERT_PRIORITY", "info")

        backend_http = httpx.AsyncClient(base_url=dashboard_url, timeout=10.0)
        client = HermesClient(backend_http, hmac_secret)
        memory = PersistentMemory(redis_asyncio.from_url(redis_url, decode_responses=True))

        command_handler = None
        updates_client = None
        if bot_token and chat_id:
            telegram_http = httpx.AsyncClient(timeout=35.0)
            alert_sink = TelegramAlertService(bot_token, chat_id, telegram_http, min_priority=min_priority)
            updates_client = TelegramUpdatesClient(bot_token, telegram_http)
            command_handler = TelegramCommandHandler(client, chat_id)
        else:
            from watchdog.heartbeat_watchdog import LoggingAlertSink

            alert_sink = LoggingAlertSink()
            log.warning("hermes_telegram_not_configured", detail="alerts will only be logged, not sent")

        app = HermesApp(client, memory, alert_sink, command_handler, updates_client)
        await app.run_forever()

    asyncio.run(main())
