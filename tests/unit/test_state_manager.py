from datetime import datetime, timezone

import fakeredis
import pytest

from common import redis_keys
from common.enums import AssetClass
from engine.connectors.paper import PaperConnector
from engine.connectors.price_feed import ReplayPriceFeed
from engine.core.repository import InMemoryTradeRepository
from engine.core.state_manager import StateManager
from engine.risk.risk_config import RiskConfig
from engine.risk.safe_mode import SafeModeManager
from engine.models.order import Order
from common.enums import OrderSide, OrderType

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_state_manager():
    redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    repo = InMemoryTradeRepository()
    return StateManager(redis_client, repo), redis_client, repo


@pytest.mark.asyncio
async def test_persist_hot_state_writes_core_keys():
    manager, redis_client, _ = make_state_manager()
    safe_mode = SafeModeManager(RiskConfig())

    await manager.persist_hot_state(
        equity=100_000.0, daily_pnl_pct=-0.01, drawdown_pct=0.05, peak_equity=105_000.0,
        gross_exposure_pct=0.3, safe_mode=safe_mode, now=T0,
    )

    assert await redis_client.get(redis_keys.STATE_EQUITY) == "100000.0"
    assert await redis_client.get(redis_keys.STATE_DRAWDOWN) == "0.05"
    assert await redis_client.hgetall(redis_keys.STATE_SAFE_MODE) == {}  # inactive -> no hash


@pytest.mark.asyncio
async def test_persist_hot_state_writes_safe_mode_hash_when_active():
    manager, redis_client, _ = make_state_manager()
    safe_mode = SafeModeManager(RiskConfig())
    safe_mode.activate("daily_loss_breaker", halt_new_entries=False, requires_manual_restart=False, now=T0)

    await manager.persist_hot_state(
        equity=100_000.0, daily_pnl_pct=-0.03, drawdown_pct=0.02, peak_equity=100_000.0,
        gross_exposure_pct=0.1, safe_mode=safe_mode, now=T0,
    )

    hash_data = await redis_client.hgetall(redis_keys.STATE_SAFE_MODE)
    assert hash_data["phase"] == "entry_block"
    assert hash_data["triggered_by"] == "daily_loss_breaker"


@pytest.mark.asyncio
async def test_strategy_state_roundtrip_prefers_redis():
    manager, redis_client, repo = make_state_manager()
    await manager.save_strategy_state("strat_1", {"foo": "bar"})

    assert await manager.load_strategy_state("strat_1") == {"foo": "bar"}
    # Also persisted to the cold repository.
    assert await repo.load_strategy_state("strat_1") == {"foo": "bar"}


@pytest.mark.asyncio
async def test_load_strategy_state_falls_back_to_repository():
    manager, redis_client, repo = make_state_manager()
    await repo.save_strategy_state("strat_1", {"cold": True})
    # Redis has nothing for this key.
    assert await manager.load_strategy_state("strat_1") == {"cold": True}


@pytest.mark.asyncio
async def test_recover_state_adopts_untracked_live_positions():
    manager, redis_client, repo = make_state_manager()
    feed = ReplayPriceFeed()
    connector = PaperConnector("paper1", AssetClass.CRYPTO, feed, initial_capital=100_000.0)
    await connector.connect({})
    feed.set_price("BTC/USD", 100.0)
    await connector.place_order(Order(asset="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=5))

    report = await manager.recover_state("paper1", connector, strategy_id="strat_1")

    assert report.adopted_positions == ["BTC/USD"]
    assert report.orphaned_trades_closed == []
    assert len(await repo.get_open_trades("strat_1")) == 1


@pytest.mark.asyncio
async def test_recover_state_closes_orphaned_trades():
    manager, redis_client, repo = make_state_manager()
    feed = ReplayPriceFeed()
    connector = PaperConnector("paper1", AssetClass.CRYPTO, feed, initial_capital=100_000.0)
    await connector.connect({})

    # DB thinks a trade is open, but the venue (paper connector) holds nothing —
    # e.g. the watchdog flattened it while the Engine was down.
    await repo.open_trade("strat_1", "paper1", "BTC/USD", "long", 5, T0, 100.0, 0.0)

    report = await manager.recover_state("paper1", connector, strategy_id="strat_1")

    assert report.orphaned_trades_closed
    assert report.adopted_positions == []
    assert await repo.get_open_trades("strat_1") == []
