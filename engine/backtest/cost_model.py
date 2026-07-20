"""Transaction cost modeling (DOC 3 §5): percentage maker/taker fees, optional
per-unit commission, and a pluggable slippage model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from common.enums import AssetClass


class SlippageModel(str, Enum):
    FIXED_BPS = "fixed_bps"
    VOLUME_PROPORTIONAL = "volume_proportional"
    LINEAR_IMPACT = "linear_impact"


@dataclass(frozen=True)
class TransactionCostModel:
    maker_fee: float = 0.0
    taker_fee: float = 0.0
    commission_per_unit: float = 0.0
    slippage_model: SlippageModel = SlippageModel.FIXED_BPS
    slippage_bps: float = 0.0

    def compute_fee(self, notional: float, quantity: float, is_maker: bool = False) -> float:
        pct_fee = abs(notional) * (self.maker_fee if is_maker else self.taker_fee)
        commission = abs(quantity) * self.commission_per_unit
        return pct_fee + commission

    def apply_slippage(self, price: float, is_buy: bool, quantity: float = 0.0, bar_volume: float = 0.0) -> float:
        fraction = self._slippage_fraction(quantity, bar_volume)
        return price * (1 + fraction) if is_buy else price * (1 - fraction)

    def _slippage_fraction(self, quantity: float, bar_volume: float) -> float:
        base = self.slippage_bps / 10_000

        if self.slippage_model == SlippageModel.FIXED_BPS:
            return base

        participation = abs(quantity) / bar_volume if bar_volume > 0 else 0.0

        if self.slippage_model == SlippageModel.VOLUME_PROPORTIONAL:
            return base * participation if bar_volume > 0 else base

        if self.slippage_model == SlippageModel.LINEAR_IMPACT:
            # Base slippage plus an additional linear market-impact term
            # proportional to how large the order is relative to bar volume.
            return base * (1 + participation)

        raise ValueError(f"unknown slippage model: {self.slippage_model}")


# Default per-asset-class cost tables (DOC 3 §5 examples).
def default_cost_model(asset_class: AssetClass) -> TransactionCostModel:
    if asset_class == AssetClass.CRYPTO:
        return TransactionCostModel(maker_fee=0.001, taker_fee=0.0015, slippage_bps=5.0)
    if asset_class == AssetClass.FUTURES:
        return TransactionCostModel(commission_per_unit=2.50, slippage_bps=2.0)
    if asset_class == AssetClass.FOREX:
        return TransactionCostModel(slippage_bps=12.0)
    if asset_class == AssetClass.STOCKS:
        return TransactionCostModel(taker_fee=0.0005, slippage_bps=5.0)
    # options, prediction markets: conservative generic default
    return TransactionCostModel(taker_fee=0.001, slippage_bps=10.0)
