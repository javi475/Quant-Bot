import pytest

from common.enums import AssetClass
from engine.backtest.cost_model import SlippageModel, TransactionCostModel, default_cost_model


def test_compute_fee_percentage_and_commission():
    model = TransactionCostModel(maker_fee=0.001, taker_fee=0.0015, commission_per_unit=2.5)
    fee = model.compute_fee(notional=10_000, quantity=10, is_maker=False)
    assert fee == pytest.approx(10_000 * 0.0015 + 10 * 2.5)


def test_compute_fee_maker_vs_taker():
    model = TransactionCostModel(maker_fee=0.001, taker_fee=0.002)
    maker_fee = model.compute_fee(notional=1000, quantity=1, is_maker=True)
    taker_fee = model.compute_fee(notional=1000, quantity=1, is_maker=False)
    assert maker_fee == pytest.approx(1.0)
    assert taker_fee == pytest.approx(2.0)


def test_fixed_bps_slippage_buy_and_sell():
    model = TransactionCostModel(slippage_model=SlippageModel.FIXED_BPS, slippage_bps=10.0)
    buy_price = model.apply_slippage(100.0, is_buy=True)
    sell_price = model.apply_slippage(100.0, is_buy=False)
    assert buy_price == pytest.approx(100.10)
    assert sell_price == pytest.approx(99.90)


def test_volume_proportional_slippage_scales_with_participation():
    model = TransactionCostModel(slippage_model=SlippageModel.VOLUME_PROPORTIONAL, slippage_bps=100.0)
    small_order = model.apply_slippage(100.0, is_buy=True, quantity=1, bar_volume=1000)
    large_order = model.apply_slippage(100.0, is_buy=True, quantity=500, bar_volume=1000)
    assert small_order < large_order


def test_volume_proportional_falls_back_to_base_when_no_volume():
    model = TransactionCostModel(slippage_model=SlippageModel.VOLUME_PROPORTIONAL, slippage_bps=10.0)
    price = model.apply_slippage(100.0, is_buy=True, quantity=10, bar_volume=0)
    assert price == pytest.approx(100.10)


def test_linear_impact_worse_than_fixed_bps_for_same_participation():
    fixed = TransactionCostModel(slippage_model=SlippageModel.FIXED_BPS, slippage_bps=10.0)
    impact = TransactionCostModel(slippage_model=SlippageModel.LINEAR_IMPACT, slippage_bps=10.0)
    fixed_price = fixed.apply_slippage(100.0, is_buy=True, quantity=100, bar_volume=1000)
    impact_price = impact.apply_slippage(100.0, is_buy=True, quantity=100, bar_volume=1000)
    assert impact_price > fixed_price


def test_unknown_slippage_model_raises():
    model = TransactionCostModel(slippage_model="bogus")
    with pytest.raises(ValueError):
        model.apply_slippage(100.0, is_buy=True)


@pytest.mark.parametrize(
    "asset_class",
    [AssetClass.CRYPTO, AssetClass.FUTURES, AssetClass.FOREX, AssetClass.STOCKS, AssetClass.OPTIONS],
)
def test_default_cost_model_returns_valid_model(asset_class):
    model = default_cost_model(asset_class)
    assert isinstance(model, TransactionCostModel)
    assert model.slippage_bps >= 0
