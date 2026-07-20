"""Persistent memory (DOC 5 §11): Redis-backed key/value store namespaced
under `hermes:` so it never collides with the Engine's own Redis keys
(common.redis_keys). The three named timestamp keys match DOC 5's schema
verbatim; every other job's last-run tracking uses a generic
`hermes:last_run:{job_name}` key instead of inventing a new named constant
per job, and each history list carries its own documented retention window.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

KEY_PREFIX = "hermes:"

LAST_DAILY_REPORT = KEY_PREFIX + "last_daily_report"
LAST_WEEKLY_BACKTEST = KEY_PREFIX + "last_weekly_backtest"
LAST_SELF_IMPROVEMENT = KEY_PREFIX + "last_self_improvement"
CRON_SCHEDULE_KEY = KEY_PREFIX + "cron_schedule"
SAFE_MODE_ALERTED_KEY = KEY_PREFIX + "safe_mode_alerted"

RISK_EVENT_HISTORY = KEY_PREFIX + "risk_event_history"
RISK_EVENT_HISTORY_TTL_SECONDS = 90 * 86400
CONNECTOR_HEALTH_HISTORY = KEY_PREFIX + "connector_health_history"
CONNECTOR_HEALTH_HISTORY_TTL_SECONDS = 7 * 86400
SYSTEM_METRICS_HISTORY = KEY_PREFIX + "system_metrics_history"
SYSTEM_METRICS_HISTORY_TTL_SECONDS = 30 * 86400

PROPOSAL_TTL_SECONDS = 365 * 86400
MAX_HISTORY_LENGTH = 500  # bound unbounded list growth regardless of TTL

_NAMED_LAST_RUN_KEYS = {
    "daily_report": LAST_DAILY_REPORT,
    "weekly_backtest": LAST_WEEKLY_BACKTEST,
    "self_improvement_proposal": LAST_SELF_IMPROVEMENT,
}


def _last_run_key(job_name: str) -> str:
    return _NAMED_LAST_RUN_KEYS.get(job_name, f"{KEY_PREFIX}last_run:{job_name}")


class PersistentMemory:
    def __init__(self, redis_client: Any) -> None:
        self.redis = redis_client

    # ----- Cron last-run tracking -----

    async def get_last_run(self, job_name: str) -> Optional[datetime]:
        raw = await self.redis.get(_last_run_key(job_name))
        return datetime.fromisoformat(raw) if raw else None

    async def set_last_run(self, job_name: str, when: datetime) -> None:
        await self.redis.set(_last_run_key(job_name), when.isoformat())

    # ----- Generic JSON storage -----

    async def get_json(self, key: str) -> Optional[Any]:
        raw = await self.redis.get(key)
        return json.loads(raw) if raw else None

    async def set_json(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        payload = json.dumps(value)
        if ttl_seconds:
            await self.redis.set(key, payload, ex=ttl_seconds)
        else:
            await self.redis.set(key, payload)

    async def append_history(
        self, key: str, entry: dict, ttl_seconds: int, max_length: int = MAX_HISTORY_LENGTH
    ) -> None:
        history = await self.get_json(key) or []
        history.append(entry)
        if len(history) > max_length:
            history = history[-max_length:]
        await self.set_json(key, history, ttl_seconds=ttl_seconds)

    async def record_risk_event(self, event: dict) -> None:
        await self.append_history(RISK_EVENT_HISTORY, event, RISK_EVENT_HISTORY_TTL_SECONDS)

    async def record_connector_health(self, entry: dict) -> None:
        await self.append_history(CONNECTOR_HEALTH_HISTORY, entry, CONNECTOR_HEALTH_HISTORY_TTL_SECONDS)

    async def record_system_metrics(self, entry: dict) -> None:
        await self.append_history(SYSTEM_METRICS_HISTORY, entry, SYSTEM_METRICS_HISTORY_TTL_SECONDS)

    # ----- Safe-mode alert dedup -----
    # DOC 5 §7 pitfalls calls out alert deduplication explicitly: without
    # this, safe_mode_check (every 15 min) would re-alert on the same still-
    # active episode every single run instead of once per new trigger.

    async def has_alerted_safe_mode(self, triggered_by: str, phase: str) -> bool:
        current = await self.get_json(SAFE_MODE_ALERTED_KEY)
        return (
            current is not None
            and current.get("triggered_by") == triggered_by
            and current.get("phase") == phase
        )

    async def mark_safe_mode_alerted(self, triggered_by: str, phase: str) -> None:
        await self.set_json(SAFE_MODE_ALERTED_KEY, {"triggered_by": triggered_by, "phase": phase})

    async def clear_safe_mode_alert(self) -> None:
        await self.redis.delete(SAFE_MODE_ALERTED_KEY)

    # ----- Proposal tracking -----
    # The self-improvement proposal *workflow* isn't built this session (see
    # hermes/jobs.py) — these just give it somewhere to persist to once it
    # exists, matching the DOC 5 §11 key schema now rather than later.

    async def get_proposal_approved(self, proposal_id: str) -> Optional[dict]:
        return await self.get_json(f"{KEY_PREFIX}proposal_{proposal_id}_approved")

    async def set_proposal_approved(self, proposal_id: str, value: dict) -> None:
        await self.set_json(f"{KEY_PREFIX}proposal_{proposal_id}_approved", value, ttl_seconds=PROPOSAL_TTL_SECONDS)

    async def get_proposal_outcome(self, proposal_id: str) -> Optional[dict]:
        return await self.get_json(f"{KEY_PREFIX}proposal_{proposal_id}_outcome")

    async def set_proposal_outcome(self, proposal_id: str, value: dict) -> None:
        await self.set_json(f"{KEY_PREFIX}proposal_{proposal_id}_outcome", value, ttl_seconds=PROPOSAL_TTL_SECONDS)
