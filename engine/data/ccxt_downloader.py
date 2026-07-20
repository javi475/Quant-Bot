"""Historical OHLCV downloader using ccxt's public (keyless) endpoints (DOC 1
§3.7). Used to backfill the `market_data` hypertable before a live crypto
connector exists.

NOTE: this module makes real network calls to an exchange's public REST API
and has intentionally not been exercised by this session's automated test
suite (no network access in this environment, and hitting a live exchange
from unit tests would be slow/flaky). Verify it manually against a real
exchange before relying on it: e.g.
    asyncio.run(download_ohlcv("binance", "BTC/USDT", Timeframe.H1, since, until))
"""

from __future__ import annotations

from datetime import datetime, timezone

from common.enums import Timeframe
from sdk.ate_smp.models.bar import Bar

DEFAULT_FETCH_LIMIT = 1000


async def download_ohlcv(
    exchange_id: str,
    symbol: str,
    timeframe: Timeframe,
    since: datetime,
    until: datetime,
    limit: int = DEFAULT_FETCH_LIMIT,
) -> list[Bar]:
    """Downloads OHLCV bars for `symbol` on `exchange_id` between `since` and
    `until` (both timezone-aware), paginating through the exchange's public
    fetch_ohlcv endpoint. No API credentials required."""
    import ccxt.async_support as ccxt

    if not hasattr(ccxt, exchange_id):
        raise ValueError(f"unknown ccxt exchange id: {exchange_id}")

    exchange = getattr(ccxt, exchange_id)()
    bars: list[Bar] = []

    try:
        since_ms = int(since.timestamp() * 1000)
        until_ms = int(until.timestamp() * 1000)
        cursor = since_ms

        while cursor < until_ms:
            candles = await exchange.fetch_ohlcv(symbol, timeframe=timeframe.value, since=cursor, limit=limit)
            if not candles:
                break

            for candle in candles:
                ts_ms, open_, high, low, close, volume = candle
                if ts_ms >= until_ms:
                    break
                bars.append(
                    Bar(
                        asset=symbol,
                        timeframe=timeframe,
                        timestamp=datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
                        open=open_,
                        high=high,
                        low=low,
                        close=close,
                        volume=volume,
                    )
                )

            if len(candles) < limit:
                break
            cursor = candles[-1][0] + 1
    finally:
        await exchange.close()

    return bars
