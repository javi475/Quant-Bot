"""DOC 2 §6 /api/trades: trade history (US-036)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request

from backend.app.auth.dependencies import get_current_subject

router = APIRouter(prefix="/api/trades", tags=["trades"], dependencies=[Depends(get_current_subject)])


@router.get("")
async def list_trades(request: Request, strategy_id: Optional[str] = None) -> list[dict]:
    trades = await request.app.state.trade_repository.list_trades(strategy_id)
    return [
        {
            "trade_id": t.trade_id,
            "strategy_id": t.strategy_id,
            "asset": t.asset,
            "side": t.side,
            "quantity": t.quantity,
            "entry_time": t.entry_time.isoformat(),
            "entry_price": t.entry_price,
            "exit_time": t.exit_time.isoformat() if t.exit_time else None,
            "exit_price": t.exit_price,
            "pnl": t.pnl,
        }
        for t in trades
    ]
