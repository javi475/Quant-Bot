import { useEngineState } from "../api/hooks";
import { StatTile } from "../components/StatTile";

function formatCurrency(value: number): string {
  return value.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 });
}

export function OverviewPage() {
  const { data: state, isLoading, isError, error } = useEngineState();

  if (isLoading) {
    return <p className="text-slate-400">Loading engine state...</p>;
  }
  if (isError || !state) {
    return (
      <p className="text-red-400">
        Could not reach the Engine: {error instanceof Error ? error.message : "unknown error"}
      </p>
    );
  }

  const strategyEntries = Object.entries(state.strategies);

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-white">Overview</h1>

      <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatTile label="Equity" value={formatCurrency(state.equity)} />
        <StatTile
          label="Unrealized P&L"
          value={formatCurrency(state.unrealized_pnl)}
          tone={state.unrealized_pnl >= 0 ? "good" : "bad"}
        />
        <StatTile label="Open Positions" value={String(state.open_position_count)} />
        <StatTile label="Gross Exposure" value={formatCurrency(state.gross_exposure_value)} />
      </div>

      <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Engine Status</div>
          <div className={`mt-1 text-lg font-semibold ${state.halted ? "text-red-400" : "text-emerald-400"}`}>
            {state.halted ? "Halted" : "Running"}
          </div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Safe Mode</div>
          <div className={`mt-1 text-lg font-semibold ${state.safe_mode.active ? "text-amber-400" : "text-emerald-400"}`}>
            {state.safe_mode.active ? `Active (${state.safe_mode.phase})` : "Inactive"}
          </div>
          {state.safe_mode.active && (
            <div className="mt-1 text-xs text-slate-500">
              Triggered by {state.safe_mode.triggered_by}
              {state.safe_mode.requires_manual_restart ? " — requires manual restart" : ""}
            </div>
          )}
        </div>
      </div>

      <h2 className="mb-3 text-lg font-semibold text-white">Strategies</h2>
      {strategyEntries.length === 0 ? (
        <p className="text-sm text-slate-500">No strategies loaded yet.</p>
      ) : (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-500">
              <th className="py-2">Strategy ID</th>
              <th className="py-2">Status</th>
              <th className="py-2">Source</th>
              <th className="py-2">Connector</th>
            </tr>
          </thead>
          <tbody>
            {strategyEntries.map(([id, s]) => (
              <tr key={id} className="border-b border-slate-900">
                <td className="py-2 font-mono text-slate-300">{id}</td>
                <td className={`py-2 ${s.enabled ? "text-emerald-400" : "text-slate-500"}`}>
                  {s.enabled ? "Enabled" : "Disabled"}
                </td>
                <td className="py-2 text-slate-400">{s.webhook_driven ? "TradingView webhook" : "Strategy code"}</td>
                <td className="py-2 text-slate-400">{s.connector_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
