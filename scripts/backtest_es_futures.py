"""Standalone ES futures backtest runner.

No CME futures connector is built yet (only ccxt/crypto exists in this
codebase), so this pulls real daily OHLCV for the continuous front-month
E-mini S&P 500 future (Yahoo Finance ticker "ES=F") via yfinance and feeds
it straight into the real M3 backtest engine (BacktestService ->
BacktestRunner -> WalkForwardAnalyzer -> MonteCarloSimulator) against the
reference RSI(2) mean-reversion strategy. This is a real backtest against
real historical data, not a simulation of one.

Usage:
    .venv/Scripts/python.exe scripts/backtest_es_futures.py [--years N] [--capital N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yfinance as yf

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "sdk"))

from backend.app.services.backtest_service import BacktestService, BacktestServiceError
from common.enums import AssetClass, Timeframe
from sdk.ate_smp.models.bar import Bar
from sdk.ate_smp.models.strategy_config import StrategyConfig

SYMBOL = "ES=F"
ASSET_NAME = "ES"


def fetch_bars(years: int) -> list[Bar]:
    df = yf.Ticker(SYMBOL).history(period=f"{years}y", interval="1d", auto_adjust=False)
    if df.empty:
        raise RuntimeError(f"yfinance returned no data for {SYMBOL} — check network access / ticker validity")

    bars: list[Bar] = []
    for ts, row in df.iterrows():
        if row[["Open", "High", "Low", "Close"]].isna().any():
            continue
        bars.append(
            Bar(
                asset=ASSET_NAME,
                timeframe=Timeframe.D1,
                timestamp=ts.to_pydatetime(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]) if not row.isna().get("Volume", False) else 0.0,
            )
        )
    bars.sort(key=lambda b: b.timestamp)
    return bars


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--capital", type=float, default=100_000.0)
    args = parser.parse_args()

    print(f"Fetching {args.years}y of daily ES=F bars from Yahoo Finance...")
    bars = fetch_bars(args.years)
    print(f"Got {len(bars)} bars: {bars[0].timestamp.date()} -> {bars[-1].timestamp.date()}")

    source_path = Path(__file__).resolve().parent.parent / "example_strategies" / "rsi_mean_reversion.py"
    source_code = source_path.read_text()

    config = StrategyConfig(
        asset_class=AssetClass.FUTURES,
        symbols=(ASSET_NAME,),
        timeframes=(Timeframe.D1,),
    )

    service = BacktestService()
    try:
        summary = service.run_backtest(
            source_code=source_code,
            class_name="RsiMeanReversionStrategy",
            config=config,
            bars=bars,
            initial_capital=args.capital,
        )
    except BacktestServiceError as exc:
        print(f"Backtest failed: {exc}")
        sys.exit(1)

    print("\n=== Backtest results (RSI(2) mean-reversion on ES=F, daily) ===")
    for key, value in summary.metrics.items():
        print(f"  {key}: {value}")

    if summary.walk_forward:
        print("\n=== Walk-forward ===")
        for key, value in summary.walk_forward.items():
            print(f"  {key}: {value}")

    if summary.monte_carlo:
        print("\n=== Monte Carlo ===")
        for key, value in summary.monte_carlo.items():
            print(f"  {key}: {value}")

    print(f"\nGates passed: {summary.gates_passed}")
    if summary.gate_failures:
        print("Gate failures:")
        for failure in summary.gate_failures:
            print(f"  - {failure}")


if __name__ == "__main__":
    main()
