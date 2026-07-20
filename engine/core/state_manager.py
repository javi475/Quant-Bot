"""Hot-state persistence (Redis) and startup reconciliation (DOC 2 §2.8, §9).
On recovery, the connector (venue) is the source of truth: any discrepancy
between Postgres's last-known open trades and the connector's actual
positions is resolved in the connector's favor, since that's what's really
happening with real money/simulated capital.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from common import redis_keys
from engine.connectors.base import ConnectorBase
from engine.core.repository import TradeRepository
from engine.risk.safe_mode import SafeModeManager


@dataclass(frozen=True)
class ReconciliationReport:
    adopted_positions: list[str]  # assets found live but with no matching open trade record
    orphaned_trades_closed: list[str]  # trade_ids closed because the venue no longer holds them


class StateManager:
    def __init__(self, redis_client: Any, repository: TradeRepository) -> None:
        self.redis = redis_client
        self.repository = repository

    async def persist_hot_state(
        self,
        equity: float,
        daily_pnl_pct: float,
        drawdown_pct: float,
        peak_equity: float,
        gross_exposure_pct: float,
        safe_mode: SafeModeManager,
        now: datetime,
    ) -> None:
        pipe = self.redis.pipeline()
        pipe.set(redis_keys.STATE_EQUITY, equity)
        pipe.set(redis_keys.STATE_PNL_DAILY, daily_pnl_pct)
        pipe.set(redis_keys.STATE_DRAWDOWN, drawdown_pct)
        pipe.set(redis_keys.STATE_PEAK_EQUITY, peak_equity)
        pipe.set(redis_keys.STATE_EXPOSURE_GROSS, gross_exposure_pct)

        if safe_mode.is_active:
            pipe.hset(
                redis_keys.STATE_SAFE_MODE,
                mapping={
                    "phase": safe_mode.phase.value,
                    "triggered_by": safe_mode.triggered_by or "",
                    "halt_new_entries": str(safe_mode.halt_new_entries),
                    "requires_manual_restart": str(safe_mode.requires_manual_restart),
                },
            )
            pipe.expire(redis_keys.STATE_SAFE_MODE, redis_keys.SAFE_MODE_TTL_SECONDS)
        else:
            pipe.delete(redis_keys.STATE_SAFE_MODE)

        await pipe.execute()

    async def persist_positions(self, positions_by_connector: dict[str, list[dict]]) -> None:
        await self.redis.set(redis_keys.STATE_POSITIONS, json.dumps(positions_by_connector))

    async def save_strategy_state(self, strategy_id: str, state: dict[str, Any]) -> None:
        await self.redis.set(
            redis_keys.strategy_state_key(strategy_id),
            json.dumps(state),
            ex=redis_keys.STRATEGY_STATE_TTL_SECONDS,
        )
        await self.repository.save_strategy_state(strategy_id, state)

    async def load_strategy_state(self, strategy_id: str) -> Optional[dict[str, Any]]:
        raw = await self.redis.get(redis_keys.strategy_state_key(strategy_id))
        if raw is not None:
            return json.loads(raw)
        return await self.repository.load_strategy_state(strategy_id)

    async def recover_state(
        self, connector_id: str, connector: ConnectorBase, strategy_id: Optional[str] = None
    ) -> ReconciliationReport:
        open_trades = await self.repository.get_open_trades(strategy_id)
        live_positions = await connector.get_all_positions()
        live_assets = {p.asset for p in live_positions}
        trade_assets = {t.asset for t in open_trades}

        orphaned_closed: list[str] = []
        for trade in open_trades:
            if trade.asset not in live_assets:
                # Venue no longer holds this position (e.g. watchdog emergency
                # flatten while the Engine was down) — close it out using its
                # own entry price as a conservative best-effort mark, since we
                # have no better price reference during recovery.
                await self.repository.close_trade(
                    trade.trade_id, datetime.now(timezone.utc), trade.entry_price, 0.0
                )
                orphaned_closed.append(trade.trade_id)

        adopted: list[str] = []
        for position in live_positions:
            if position.asset not in trade_assets:
                side = "long" if position.quantity > 0 else "short"
                await self.repository.open_trade(
                    strategy_id or "",
                    connector_id,
                    position.asset,
                    side,
                    abs(position.quantity),
                    position.opened_at,
                    position.entry_price,
                    0.0,
                )
                adopted.append(position.asset)

        return ReconciliationReport(adopted_positions=adopted, orphaned_trades_closed=orphaned_closed)
