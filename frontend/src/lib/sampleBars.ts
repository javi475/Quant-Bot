/** Generates a deterministic synthetic random-walk bar series for exercising
 * the backtesting page without a wired-up historical data source (the
 * backend's /api/backtests endpoint takes bars directly in the request —
 * see backend/app/services/backtest_service.py for why). Not real market
 * data; useful for confirming the pipeline runs end-to-end. */
export function generateSampleBars(asset: string, timeframe: string, days: number) {
  let seed = 42;
  const random = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };

  const bars = [];
  let price = 100;
  const start = new Date("2021-01-01T00:00:00Z");

  for (let i = 0; i < days; i++) {
    const drift = (random() - 0.5) * 0.02;
    price = Math.max(1, price * (1 + drift));
    const high = price * (1 + random() * 0.01);
    const low = price * (1 - random() * 0.01);
    const timestamp = new Date(start.getTime() + i * 24 * 60 * 60 * 1000).toISOString();
    bars.push({
      asset,
      timeframe,
      timestamp,
      open: Number(price.toFixed(4)),
      high: Number(Math.max(high, price).toFixed(4)),
      low: Number(Math.min(low, price).toFixed(4)),
      close: Number(price.toFixed(4)),
      volume: 100,
    });
  }
  return bars;
}
