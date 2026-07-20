from datetime import datetime, timedelta, timezone

import pytest

from common.enums import RiskEventSeverity, RiskEventType
from engine.core.repository import InMemoryTradeRepository, RiskEventRecord

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def repo():
    return InMemoryTradeRepository()


@pytest.mark.asyncio
async def test_open_and_get_open_trades(repo):
    trade_id = await repo.open_trade("strat_1", "paper1", "BTC/USD", "long", 10, T0, 100.0, 1.0)
    open_trades = await repo.get_open_trades()
    assert len(open_trades) == 1
    assert open_trades[0].trade_id == trade_id
    assert not open_trades[0].is_closed


@pytest.mark.asyncio
async def test_get_open_trades_filters_by_strategy(repo):
    await repo.open_trade("strat_1", "paper1", "BTC/USD", "long", 10, T0, 100.0, 1.0)
    await repo.open_trade("strat_2", "paper1", "ETH/USD", "long", 5, T0, 10.0, 0.5)
    assert len(await repo.get_open_trades("strat_1")) == 1
    assert len(await repo.get_open_trades("strat_2")) == 1
    assert len(await repo.get_open_trades()) == 2


@pytest.mark.asyncio
async def test_close_trade_computes_long_pnl(repo):
    trade_id = await repo.open_trade("strat_1", "paper1", "BTC/USD", "long", 10, T0, 100.0, 1.0)
    await repo.close_trade(trade_id, T0 + timedelta(hours=1), 110.0, 1.0)

    open_trades = await repo.get_open_trades()
    assert open_trades == []

    trade = repo.all_trades()[0]
    assert trade.is_closed
    assert trade.pnl == pytest.approx((110.0 - 100.0) * 10 - 1.0 - 1.0)


@pytest.mark.asyncio
async def test_close_trade_computes_short_pnl(repo):
    trade_id = await repo.open_trade("strat_1", "paper1", "BTC/USD", "short", 5, T0, 100.0, 0.0)
    await repo.close_trade(trade_id, T0 + timedelta(hours=1), 90.0, 0.0)
    trade = repo.all_trades()[0]
    assert trade.pnl == pytest.approx((100.0 - 90.0) * 5)


@pytest.mark.asyncio
async def test_close_unknown_trade_raises(repo):
    with pytest.raises(KeyError):
        await repo.close_trade("nonexistent", T0, 100.0, 0.0)


@pytest.mark.asyncio
async def test_record_and_list_risk_events(repo):
    event = RiskEventRecord(
        event_type=RiskEventType.DAILY_LOSS_BREAKER,
        severity=RiskEventSeverity.CRITICAL,
        description="test event",
        occurred_at=T0,
    )
    await repo.record_risk_event(event)
    assert repo.all_risk_events() == [event]


@pytest.mark.asyncio
async def test_strategy_state_roundtrip(repo):
    assert await repo.load_strategy_state("strat_1") is None
    await repo.save_strategy_state("strat_1", {"foo": "bar"})
    assert await repo.load_strategy_state("strat_1") == {"foo": "bar"}
