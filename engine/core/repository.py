"""Cold-storage persistence boundary (DOC 2 §2.8: trades, fills, risk_events,
strategy_state_log tables). Defined as a Protocol so the Engine's logic can be
fully unit-tested against `InMemoryTradeRepository` without a live Postgres —
this dev environment has no Docker available, so `PostgresTradeRepository` is
a real implementation that has NOT been exercised against a live database
this session (same treatment as the rest of the persistence layer since M0).
"""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol

from common.enums import RiskEventSeverity, RiskEventType


@dataclass
class TradeRecord:
    trade_id: str
    strategy_id: str
    connector_id: str
    asset: str
    side: str  # "long" | "short"
    quantity: float
    entry_time: datetime
    entry_price: float
    entry_fee: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_fee: float = 0.0

    @property
    def is_closed(self) -> bool:
        return self.exit_time is not None

    @property
    def pnl(self) -> Optional[float]:
        if not self.is_closed:
            return None
        direction = 1.0 if self.side == "long" else -1.0
        return (
            direction * (self.exit_price - self.entry_price) * self.quantity
            - self.entry_fee
            - self.exit_fee
        )


@dataclass
class RiskEventRecord:
    event_type: RiskEventType
    severity: RiskEventSeverity
    description: str
    action_taken: str = ""
    safe_mode_activated: bool = False
    strategy_id: Optional[str] = None
    connector_id: Optional[str] = None
    symbol: Optional[str] = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now())
    metadata: dict[str, Any] = field(default_factory=dict)


class TradeRepository(Protocol):
    async def open_trade(
        self,
        strategy_id: str,
        connector_id: str,
        asset: str,
        side: str,
        quantity: float,
        entry_time: datetime,
        entry_price: float,
        entry_fee: float,
    ) -> str:
        """Persists a new open trade, returns its trade_id."""
        ...

    async def close_trade(
        self, trade_id: str, exit_time: datetime, exit_price: float, exit_fee: float
    ) -> None: ...

    async def get_open_trades(self, strategy_id: Optional[str] = None) -> list[TradeRecord]: ...

    async def list_trades(self, strategy_id: Optional[str] = None) -> list[TradeRecord]:
        """All trades — open and closed — for the dashboard's trade history
        (DOC 2 §6 GET /api/trades)."""
        ...

    async def record_risk_event(self, event: RiskEventRecord) -> None: ...

    async def list_risk_events(self, strategy_id: Optional[str] = None) -> list[RiskEventRecord]:
        """DOC 2 §6 GET /api/risk/breaker-history."""
        ...

    async def save_strategy_state(self, strategy_id: str, state: dict[str, Any]) -> None: ...

    async def load_strategy_state(self, strategy_id: str) -> Optional[dict[str, Any]]: ...


class InMemoryTradeRepository:
    """Fully in-process test double — no I/O, deterministic, used by the M4
    test suite in place of a live Postgres."""

    def __init__(self) -> None:
        self._trades: dict[str, TradeRecord] = {}
        self._risk_events: list[RiskEventRecord] = []
        self._strategy_state: dict[str, dict[str, Any]] = {}
        self._id_counter = itertools.count(1)

    async def open_trade(
        self,
        strategy_id: str,
        connector_id: str,
        asset: str,
        side: str,
        quantity: float,
        entry_time: datetime,
        entry_price: float,
        entry_fee: float,
    ) -> str:
        trade_id = f"trd_{next(self._id_counter)}"
        self._trades[trade_id] = TradeRecord(
            trade_id=trade_id,
            strategy_id=strategy_id,
            connector_id=connector_id,
            asset=asset,
            side=side,
            quantity=quantity,
            entry_time=entry_time,
            entry_price=entry_price,
            entry_fee=entry_fee,
        )
        return trade_id

    async def close_trade(self, trade_id: str, exit_time: datetime, exit_price: float, exit_fee: float) -> None:
        trade = self._trades.get(trade_id)
        if trade is None:
            raise KeyError(f"unknown trade_id {trade_id}")
        trade.exit_time = exit_time
        trade.exit_price = exit_price
        trade.exit_fee = exit_fee

    async def get_open_trades(self, strategy_id: Optional[str] = None) -> list[TradeRecord]:
        return [
            t
            for t in self._trades.values()
            if not t.is_closed and (strategy_id is None or t.strategy_id == strategy_id)
        ]

    async def list_trades(self, strategy_id: Optional[str] = None) -> list[TradeRecord]:
        return [
            t for t in self._trades.values() if strategy_id is None or t.strategy_id == strategy_id
        ]

    async def record_risk_event(self, event: RiskEventRecord) -> None:
        self._risk_events.append(event)

    async def list_risk_events(self, strategy_id: Optional[str] = None) -> list[RiskEventRecord]:
        return [
            e for e in self._risk_events if strategy_id is None or e.strategy_id == strategy_id
        ]

    async def save_strategy_state(self, strategy_id: str, state: dict[str, Any]) -> None:
        self._strategy_state[strategy_id] = state

    async def load_strategy_state(self, strategy_id: str) -> Optional[dict[str, Any]]:
        return self._strategy_state.get(strategy_id)

    # Test-only helpers
    def all_trades(self) -> list[TradeRecord]:
        return list(self._trades.values())

    def all_risk_events(self) -> list[RiskEventRecord]:
        return list(self._risk_events)


class PostgresTradeRepository:
    """Real Postgres-backed implementation using the M0 SQLAlchemy models.

    NOT exercised by this session's automated tests — no Docker/Postgres is
    available in this dev environment. Verify manually once the stack is
    running (`docker compose up postgres`) before relying on it live.

    `strategy_to_deployment` maps strategy_id -> deployment UUID; full
    deployment-record lifecycle management belongs to the dashboard backend
    (M5) and isn't built yet, so callers must register deployments themselves
    before trades can be persisted here.
    """

    def __init__(self, session_factory, strategy_to_deployment: dict[str, uuid.UUID]) -> None:
        self._session_factory = session_factory
        self._strategy_to_deployment = strategy_to_deployment

    async def open_trade(
        self,
        strategy_id: str,
        connector_id: str,
        asset: str,
        side: str,
        quantity: float,
        entry_time: datetime,
        entry_price: float,
        entry_fee: float,
    ) -> str:
        from engine.persistence.models import Trade as TradeModel

        deployment_id = self._strategy_to_deployment[strategy_id]
        async with self._session_factory() as session:
            trade = TradeModel(
                deployment_id=deployment_id,
                asset=asset,
                side=side,
                quantity=quantity,
                entry_price=entry_price,
                fees=entry_fee,
                opened_at=entry_time,
            )
            session.add(trade)
            await session.commit()
            await session.refresh(trade)
            return str(trade.id)

    async def close_trade(self, trade_id: str, exit_time: datetime, exit_price: float, exit_fee: float) -> None:
        from sqlalchemy import select

        from engine.persistence.models import Trade as TradeModel

        async with self._session_factory() as session:
            result = await session.execute(select(TradeModel).where(TradeModel.id == uuid.UUID(trade_id)))
            trade = result.scalar_one()
            trade.closed_at = exit_time
            trade.exit_price = exit_price
            trade.fees = (trade.fees or 0.0) + exit_fee
            direction = 1.0 if trade.side == "long" else -1.0
            trade.realized_pnl = direction * (exit_price - trade.entry_price) * trade.quantity - trade.fees
            await session.commit()

    async def get_open_trades(self, strategy_id: Optional[str] = None) -> list[TradeRecord]:
        from sqlalchemy import select

        from engine.persistence.models import Trade as TradeModel

        async with self._session_factory() as session:
            stmt = select(TradeModel).where(TradeModel.closed_at.is_(None))
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                TradeRecord(
                    trade_id=str(row.id),
                    strategy_id=strategy_id or "",
                    connector_id="",
                    asset=row.asset,
                    side=row.side,
                    quantity=row.quantity,
                    entry_time=row.opened_at,
                    entry_price=row.entry_price,
                    entry_fee=row.fees or 0.0,
                )
                for row in rows
            ]

    async def list_trades(self, strategy_id: Optional[str] = None) -> list[TradeRecord]:
        from sqlalchemy import select

        from engine.persistence.models import Trade as TradeModel

        async with self._session_factory() as session:
            result = await session.execute(select(TradeModel))
            rows = result.scalars().all()
            return [
                TradeRecord(
                    trade_id=str(row.id),
                    strategy_id=strategy_id or "",
                    connector_id="",
                    asset=row.asset,
                    side=row.side,
                    quantity=row.quantity,
                    entry_time=row.opened_at,
                    entry_price=row.entry_price,
                    entry_fee=row.fees or 0.0,
                    exit_time=row.closed_at,
                    exit_price=row.exit_price,
                    exit_fee=0.0,
                )
                for row in rows
            ]

    async def record_risk_event(self, event: RiskEventRecord) -> None:
        from engine.persistence.models import RiskEvent as RiskEventModel

        async with self._session_factory() as session:
            session.add(
                RiskEventModel(
                    event_type=event.event_type.value,
                    severity=event.severity.value,
                    description=event.description,
                    action_taken=event.action_taken,
                    safe_mode_activated=event.safe_mode_activated,
                    symbol=event.symbol,
                    metadata_=event.metadata,
                    occurred_at=event.occurred_at,
                )
            )
            await session.commit()

    async def list_risk_events(self, strategy_id: Optional[str] = None) -> list[RiskEventRecord]:
        from sqlalchemy import select

        from common.enums import RiskEventSeverity, RiskEventType
        from engine.persistence.models import RiskEvent as RiskEventModel

        async with self._session_factory() as session:
            result = await session.execute(select(RiskEventModel))
            rows = result.scalars().all()
            return [
                RiskEventRecord(
                    event_type=RiskEventType(row.event_type),
                    severity=RiskEventSeverity(row.severity),
                    description=row.description,
                    action_taken=row.action_taken or "",
                    safe_mode_activated=row.safe_mode_activated,
                    symbol=row.symbol,
                    occurred_at=row.occurred_at,
                    metadata=row.metadata_ or {},
                )
                for row in rows
            ]

    async def save_strategy_state(self, strategy_id: str, state: dict[str, Any]) -> None:
        from engine.persistence.models import StrategyStateLog

        async with self._session_factory() as session:
            session.add(StrategyStateLog(strategy_id=uuid.UUID(strategy_id), state=state))
            await session.commit()

    async def load_strategy_state(self, strategy_id: str) -> Optional[dict[str, Any]]:
        from sqlalchemy import desc, select

        from engine.persistence.models import StrategyStateLog

        async with self._session_factory() as session:
            stmt = (
                select(StrategyStateLog)
                .where(StrategyStateLog.strategy_id == uuid.UUID(strategy_id))
                .order_by(desc(StrategyStateLog.recorded_at))
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return row.state if row else None
