import { useState } from "react";

import { useConnectors, useDeploy, useEngineState, useStrategies } from "../api/hooks";
import { ApiError } from "../api/client";

const ASSET_CLASSES = ["crypto", "futures", "options", "forex", "stocks", "prediction_markets"];
const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"];

export function DeploymentPage() {
  const { data: strategies } = useStrategies();
  const { data: connectors } = useConnectors();
  const { data: engineState } = useEngineState();
  const deploy = useDeploy();

  const [strategyId, setStrategyId] = useState("");
  const [connectorId, setConnectorId] = useState("");
  const [assetClass, setAssetClass] = useState(ASSET_CLASSES[0]);
  const [symbol, setSymbol] = useState("BTC/USD");
  const [timeframe, setTimeframe] = useState("1d");
  const [capitalAllocation, setCapitalAllocation] = useState(0.3);
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<string | null>(null);

  const alreadyRunning = strategyId ? Boolean(engineState?.strategies[strategyId]) : false;

  async function handleDeploy(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setLastResult(null);
    if (!strategyId || !connectorId) {
      setError("Select both a strategy and a connector.");
      return;
    }
    try {
      const result = await deploy.mutateAsync({
        strategy_id: strategyId,
        config: {
          asset_class: assetClass,
          symbols: [symbol],
          timeframes: [timeframe],
          parameters: {},
          regime_filter: null,
          max_position_holding_hours: null,
          connector_id: connectorId,
          capital_allocation: capitalAllocation,
        },
      });
      setLastResult(`${result.status === "hot_swapped" ? "Hot-swapped" : "Deployed"} version ${result.version}.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Deployment failed");
    }
  }

  return (
    <div>
      <h1 className="mb-2 text-2xl font-bold text-white">Deployment</h1>
      <p className="mb-6 text-sm text-slate-400">
        Deploys a strategy's active version to the Engine. Redeploying a strategy that's already running hot-swaps it
        instead of reloading from scratch.
      </p>

      <form onSubmit={handleDeploy} className="mb-6 grid grid-cols-2 gap-4 rounded-lg border border-slate-800 bg-slate-900 p-5 md:grid-cols-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-400" htmlFor="dep-strategy">
            Strategy
          </label>
          <select
            id="dep-strategy"
            value={strategyId}
            onChange={(e) => setStrategyId(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          >
            <option value="">Select...</option>
            {(strategies ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          {alreadyRunning && <p className="mt-1 text-xs text-amber-400">Already running — this will hot-swap it.</p>}
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-400" htmlFor="dep-connector">
            Connector
          </label>
          <select
            id="dep-connector"
            value={connectorId}
            onChange={(e) => setConnectorId(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          >
            <option value="">Select...</option>
            {(connectors ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.connector_type})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-400" htmlFor="dep-asset-class">
            Asset class
          </label>
          <select
            id="dep-asset-class"
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
          <label className="mb-1 block text-xs font-medium text-slate-400" htmlFor="dep-symbol">
            Symbol
          </label>
          <input
            id="dep-symbol"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          />
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-400" htmlFor="dep-timeframe">
            Timeframe
          </label>
          <select
            id="dep-timeframe"
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
          <label className="mb-1 block text-xs font-medium text-slate-400" htmlFor="dep-capital-allocation">
            Capital allocation
          </label>
          <input
            id="dep-capital-allocation"
            type="number"
            min={0.05}
            max={1}
            step={0.05}
            value={capitalAllocation}
            onChange={(e) => setCapitalAllocation(Number(e.target.value))}
            className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          />
        </div>

        <div className="col-span-2 flex items-end md:col-span-3">
          <button
            type="submit"
            disabled={deploy.isPending}
            className="rounded bg-blue-600 px-6 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {deploy.isPending ? "Deploying..." : alreadyRunning ? "Hot-swap" : "Deploy"}
          </button>
        </div>
      </form>

      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}
      {lastResult && <p className="mb-4 text-sm text-emerald-400">{lastResult}</p>}
    </div>
  );
}
