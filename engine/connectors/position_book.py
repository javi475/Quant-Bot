"""Shared position bookkeeping for connectors that track fills locally
rather than trusting a venue's own position/balance snapshot. Both
PaperConnector (which has no other source of truth) and CCXTConnector
(spot balances carry no entry-price context) apply every confirmed fill
through this same rule.
"""

from __future__ import annotations

from datetime import datetime, timezone

from engine.models.position import Position


def apply_position_delta(positions: dict[str, Position], asset: str, delta: float, fill_price: float) -> None:
    """Applies a signed fill (positive = buy, negative = sell) to `positions`
    in place: opens a new position, adds to/reduces an existing one at a
    quantity-weighted average entry price, flips direction, or closes it out
    entirely when the resulting quantity nets to zero."""
    existing = positions.get(asset)
    if existing is None:
        positions[asset] = Position(
            asset=asset,
            quantity=delta,
            entry_price=fill_price,
            current_price=fill_price,
            opened_at=datetime.now(timezone.utc),
        )
        return

    new_quantity = existing.quantity + delta
    if new_quantity == 0:
        del positions[asset]
        return

    same_direction = (existing.quantity > 0) == (delta > 0)
    if same_direction:
        total_cost = existing.entry_price * abs(existing.quantity) + fill_price * abs(delta)
        existing.entry_price = total_cost / abs(new_quantity)
    else:
        existing.entry_price = fill_price  # reduced or flipped: simplified re-basis
    existing.quantity = new_quantity
    existing.current_price = fill_price
