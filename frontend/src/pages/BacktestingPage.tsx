import { useState } from "react";

import { useRunBacktest, useStrategies } from "../api/hooks";
import { ApiError } from "../api/client";
import { generateSampleBars } from "../lib/sampleBars";
import type { BacktestSummary } from "../types/api";

const ASSET_CLASSES = ["crypto", "futures", "options", "forex", "stocks", "prediction_markets"];
const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"];

function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function ResultPanel({ result }: { result: BacktestSummary }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-5">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white">Results</h3>
        <span
          className={`rounded px-3 py-1 text-xs font-bold ${
            result.gates_passed ? "bg-emerald-900/40 text-emerald-400" : "bg-red-900/40 text-red-400"
          }`}
        >
          {result.gates_passed ? "GATES PASSED" : "GATES FAILED"}
        </span>
      </div>

      <div className="mb-4 grid grid-cols-3 gap-3 text-sm">
        {Object.entries(result.metrics).map(([key, value]) => (
          <div key={key} className="rounded border border-slate-800 p-2">
            <div className="text-xs uppercase text-slate-500">{key.replace(/_/g, " ")}</div>
            <div className="font-mono text-slate-200">{typeof value === "number" ? value.toFixed(3) : String(value)}</div>
          </div>
        ))}
      </div>

      {result.walk_forward && (
        <div className="mb-4">
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Walk-forward</h4>
          <p className="text-sm text-slate-300">
            IS Sharpe {result.walk_forward.is_sharpe.toFixed(2)} · OOS Sharpe {result.walk_forward.oos_sharpe.toFixed(2)} ·
            Degradation {formatPct(result.walk_forward.degradation_pct)} ·{" "}
            {result.walk_forward.passed ? "Passed" : "Failed"} gate
          </p>
        </div>
      )}

      {result.monte_carlo && (
        <div className="mb-4">
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Monte Carlo</h4>
          <p className="text-sm text-slate-300">
            {result.monte_carlo.iterations} iterations · Prob. of ruin {formatPct(result.monte_carlo.prob_of_ruin)} · Median
            max DD {formatPct(result.monte_carlo.max_drawdown_median)} · P95 max DD{" "}
            {formatPct(result.monte_carlo.max_drawdown_p95)}
          </p>
        </div>
      )}

      {result.gate_failures.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-red-500">Gate failures</h4>
          <ul className="list-inside list-disc text-sm text-red-300">
            {result.gate_failures.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function BacktestingPage() {
  const { data: strategies } = useStrategies();
  const runBacktest = useRunBacktest();

  const [strategyId, setStrategyId] = useState("");
  const [assetClass, setAssetClass] = useState(ASSET_CLASSES[0]);
  const [symbol, setSymbol] = useState("BTC/USD");
  const [timeframe, setTimeframe] = useState("1d");
  const [initialCapital, setInitialCapital] = useState(30000);
  const [barCount, setBarCount] = useState(0);
  const [runWalkForward, setRunWalkForward] = useState(true);
  const [runMonteCarlo, setRunMonteCarlo] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function handleRun(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!strategyId) {
      setError("Select a strategy first.");
      return;
    }
    const bars = generateSampleBars(symbol, timeframe, barCount || 250);
    try {
      await runBacktest.mutateAsync({
        strategy_id: strategyId,
        config: {
          asset_class: assetClass,
          symbols: [symbol],
          timeframes: [timeframe],
          parameters: {},
          regime_filter: null,
          max_position_holding_hours: null,
          connector_id: "",
          capital_allocation: 0.3,
        },
        bars,
        initial_capital: initialCapital,
        run_walk_forward: runWalkForward,
        run_monte_carlo: runMonteCarlo,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Backtest failed");
    }
  }

  return (
    <div>
      <h1 className="mb-2 text-2xl font-bold text-white">Backtesting</h1>
      <p className="mb-6 text-sm text-slate-400">
        Bars here are synthetic sample data generated in the browser — a real historical data feed lands with a
        future venue-connector milestone. This confirms the strategy validation → backtest → gate-check pipeline
        end-to-end.
      </p>

      <form onSubmit={handleRun} className="mb-8 grid grid-cols-2 gap-4 rounded-lg border border-slate-800 bg-slate-900 p-5 md:grid-cols-4">
        <div className="col-span-2">
          <label className="mb-1 block text-xs font-medium text-slate-400" htmlFor="bt-strategy">
            Strategy
          </label>
          <select
            id="bt-strategy"
            value={strategyId}
            onChange={(e) => setStrategyId(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          >
            <option value="">Select a strategy...</option>
            {(strategies ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-400" htmlFor="bt-asset-class">
            Asset class
          </label>
          <select
            id="bt-asset-class"
            value={assetClass}
            onChange={(e) => setAssetClass(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          >
            {ASSET_CLASSES.map((ac) => (
              <option key={ac} value={ac}>
                {ac}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-400" htmlFor="bt-timeframe">
            Timeframe
          </label>
          <select
            id="bt-timeframe"
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          >
            {TIMEFRAMES.map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-400" htmlFor="bt-symbol">
            Symbol
          </label>
          <input
            id="bt-symbol"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          />
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-400" htmlFor="bt-capital">
            Initial capital
          </label>
          <input
            id="bt-capital"
            type="number"
            min={1}
            value={initialCapital}
            onChange={(e) => setInitialCapital(Number(e.target.value))}
            className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          />
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-400" htmlFor="bt-bars">
            Sample bars
          </label>
          <input
            id="bt-bars"
            type="number"
            min={5}
            placeholder="250"
            value={barCount || ""}
            onChange={(e) => setBarCount(Number(e.target.value))}
            className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          />
        </div>

        <div className="col-span-2 flex items-end gap-4">
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={runWalkForward} onChange={(e) => setRunWalkForward(e.target.checked)} />
            Walk-forward
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={runMonteCarlo} onChange={(e) => setRunMonteCarlo(e.target.checked)} />
            Monte Carlo
          </label>
        </div>

        <div className="col-span-2 flex items-end justify-end">
          <button
            type="submit"
            disabled={runBacktest.isPending}
            className="rounded bg-blue-600 px-6 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {runBacktest.isPending ? "Running..." : "Run backtest"}
          </button>
        </div>
      </form>

      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}
      {runBacktest.data && <ResultPanel result={runBacktest.data} />}
    </div>
  );
}
