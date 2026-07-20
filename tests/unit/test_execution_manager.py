import pytest

from common.enums import AssetClass, OrderSide, OrderType
from engine.backtest.cost_model import TransactionCostModel
from engine.connectors.paper import PaperConnector
from engine.connectors.price_feed import ReplayPriceFeed
from engine.core.execution_manager import ExecutionManager
from engine.core.repository import InMemoryTradeRepository
from engine.models.order import Order


async def make_manager(spread_bps=0.0):
    feed = ReplayPriceFeed()
    connector = PaperConnector(
        connector_id="paper1",
        asset_class=AssetClass.CRYPTO,
        feed=feed,
        cost_model=TransactionCostModel(),
        initial_capital=100_000.0,
        spread_bps=spread_bps,
    )
    await connector.connect({})
    repo = InMemoryTradeRepository()
    manager = ExecutionManager({"paper1": connector}, repo)
    return manager, connector, feed, repo


@pytest.mark.asyncio
async def test_place_market_order_records_open_trade():
    manager, connector, feed, repo = await make_manager()
    feed.set_price("BTC/USD", 100.0)

    order = Order(asset="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    fill = await manager.place_order("paper1", order, "strat_1")

    assert fill is not None
    assert fill.price == pytest.approx(100.0)
    open_trades = await repo.get_open_trades("strat_1")
    assert len(open_trades) == 1
    assert open_trades[0].asset == "BTC/USD"


@pytest.mark.asyncio
async def test_closing_fill_closes_the_matching_trade():
    manager, connector, feed, repo = await make_manager()
    feed.set_price("BTC/USD", 100.0)
    await manager.place_order(
        "paper1", Order(asset="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10), "strat_1"
    )

    feed.set_price("BTC/USD", 105.0)
    await manager.place_order(
        "paper1", Order(asset="BTC/USD", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=10), "strat_1"
    )

    assert await repo.get_open_trades("strat_1") == []
    trade = repo.all_trades()[0]
    assert trade.is_closed
    assert trade.pnl == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_pending_limit_order_recorded_only_once_filled():
    manager, connector, feed, repo = await make_manager()
    feed.set_price("BTC/USD", 100.0)
    order = Order(asset="BTC/USD", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=1, limit_price=90.0)
    fill = await manager.place_order("paper1", order, "strat_1")

    assert fill is None  # not marketable yet
    assert await repo.get_open_trades("strat_1") == []

    feed.set_price("BTC/USD", 89.0)
    fills = await manager.process_pending_orders("paper1", {"BTC/USD": "strat_1"})
    assert len(fills) == 1
    assert len(await repo.get_open_trades("strat_1")) == 1


@pytest.mark.asyncio
async def test_flatten_all_closes_every_position():
    manager, connector, feed, repo = await make_manager()
    feed.set_price("BTC/USD", 100.0)
    feed.set_price("ETH/USD", 10.0)
    await manager.place_order(
        "paper1", Order(asset="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=5), "strat_1"
    )
    await manager.place_order(
        "paper1", Order(asset="ETH/USD", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=20), "strat_2"
    )

    fills = await manager.flatten_all("paper1", {"BTC/USD": "strat_1", "ETH/USD": "strat_2"})
    assert len(fills) == 2
    assert await connector.get_all_positions() == []
    assert await repo.get_open_trades() == []


@pytest.mark.asyncio
async def test_closing_fill_carries_realized_pnl_in_metadata():
    manager, connector, feed, repo = await make_manager()
    feed.set_price("BTC/USD", 100.0)
    open_fill = await manager.place_order(
        "paper1", Order(asset="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10), "strat_1"
    )
    assert "realized_pnl" not in open_fill.metadata  # opening fill: nothing realized yet

    feed.set_price("BTC/USD", 90.0)
    close_fill = await manager.place_order(
        "paper1", Order(asset="BTC/USD", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=10), "strat_1"
    )
    assert close_fill.metadata["realized_pnl"] == pytest.approx(-100.0)


@pytest.mark.asyncio
async def test_cancel_order_delegates_to_connector():
    manager, connector, feed, repo = await make_manager()
    feed.set_price("BTC/USD", 100.0)
    order = Order(asset="BTC/USD", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=1, limit_price=50.0)
    placed = await manager.connectors["paper1"].place_order(order)
    await manager.cancel_order("paper1", placed.venue_order_id)
    status = await connector.get_order_status(placed.venue_order_id)
    assert status.status.value == "cancelled"
