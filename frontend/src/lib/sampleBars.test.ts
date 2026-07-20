import { describe, expect, it } from "vitest";

import { generateSampleBars } from "./sampleBars";

describe("generateSampleBars", () => {
  it("generates the requested number of bars", () => {
    const bars = generateSampleBars("BTC/USD", "1d", 30);
    expect(bars).toHaveLength(30);
  });

  it("produces internally consistent OHLC on every bar", () => {
    const bars = generateSampleBars("BTC/USD", "1d", 100);
    for (const bar of bars) {
      expect(bar.high).toBeGreaterThanOrEqual(bar.open);
      expect(bar.high).toBeGreaterThanOrEqual(bar.close);
      expect(bar.low).toBeLessThanOrEqual(bar.open);
      expect(bar.low).toBeLessThanOrEqual(bar.close);
      expect(bar.high).toBeGreaterThanOrEqual(bar.low);
      expect(bar.volume).toBeGreaterThan(0);
    }
  });

  it("produces strictly increasing timestamps", () => {
    const bars = generateSampleBars("BTC/USD", "1d", 10);
    const timestamps = bars.map((b) => new Date(b.timestamp).getTime());
    for (let i = 1; i < timestamps.length; i++) {
      expect(timestamps[i]).toBeGreaterThan(timestamps[i - 1]);
    }
  });

  it("is deterministic for the same inputs", () => {
    const a = generateSampleBars("BTC/USD", "1d", 20);
    const b = generateSampleBars("BTC/USD", "1d", 20);
    expect(a).toEqual(b);
  });

  it("tags every bar with the requested asset and timeframe", () => {
    const bars = generateSampleBars("ETH/USD", "1h", 5);
    for (const bar of bars) {
      expect(bar.asset).toBe("ETH/USD");
      expect(bar.timeframe).toBe("1h");
    }
  });
});
