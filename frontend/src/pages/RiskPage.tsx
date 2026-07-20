import { useEffect, useState } from "react";

import { useBreakerHistory, useRiskParams, useUpdateRiskParams } from "../api/hooks";
import { ApiError } from "../api/client";
import type { RiskParams } from "../types/api";

const FIELD_GROUPS: { title: string; fields: (keyof RiskParams)[] }[] = [
  {
    title: "Position sizing",
    fields: ["kelly_multiplier", "max_risk_per_trade", "max_leverage", "min_portfolio_value"],
  },
  {
    title: "Breakers",
    fields: ["daily_loss_breaker", "max_drawdown", "drawdown_alert_1", "drawdown_alert_2", "drawdown_alert_3"],
  },
  {
    title: "Exposure & correlation",
    fields: ["max_concurrent_positions", "max_gross_exposure", "correlation_cap", "correlation_lookback_days"],
  },
  {
    title: "Safe mode recovery",
    fields: [
      "post_breaker_size_mult",
      "post_breaker_duration_hours",
      "recovery_phase_1_days",
      "recovery_phase_2_days",
      "recovery_phase_3_days",
    ],
  },
  {
    title: "Dead-man switch",
    fields: ["heartbeat_timeout_seconds", "heartbeat_interval_seconds", "watchdog_check_interval_seconds"],
  },
  {
    title: "Capital allocation",
    fields: ["per_strategy_min_allocation", "per_strategy_max_allocation", "cash_reserve_min"],
  },
];

function severityTone(severity: string): string {
  if (severity === "critical") return "text-red-400";
  if (severity === "serious") return "text-orange-400";
  if (severity === "warning") return "text-amber-400";
  return "text-slate-400";
}

export function RiskPage() {
  const { data: params, isLoading } = useRiskParams();
  const updateParams = useUpdateRiskParams();
  const { data: history } = useBreakerHistory();

  const [form, setForm] = useState<RiskParams | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (params && !form) {
      setForm(params);
    }
  }, [params, form]);

  async function handleSave(event: React.FormEvent) {
    event.preventDefault();
    if (!form) return;
    setError(null);
    setSaved(false);
    try {
      const updated = await updateParams.mutateAsync(form);
      setForm(updated);
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Update rejected");
    }
  }

  if (isLoading || !form) {
    return <p className="text-slate-400">Loading risk parameters...</p>;
  }

  return (
    <div>
      <h1 className="mb-2 text-2xl font-bold text-white">Risk Parameters</h1>
      <p className="mb-6 text-sm text-slate-400">
        Changes here are proxied straight through to the running Engine's RiskManager (DOC 4 §8) and take effect on
        its very next cycle.
      </p>

      <form onSubmit={handleSave} className="mb-8 space-y-6">
        {FIELD_GROUPS.map((group) => (
          <div key={group.title} className="rounded-lg border border-slate-800 bg-slate-900 p-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">{group.title}</h2>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              {group.fields.map((field) => (
                <div key={field}>
                  <label className="mb-1 block text-xs text-slate-500" htmlFor={field}>
                    {field.replace(/_/g, " ")}
                  </label>
                  <input
                    id={field}
                    type="number"
                    step="any"
                    value={form[field]}
                    onChange={(e) => setForm({ ...form, [field]: Number(e.target.value) })}
                    className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100"
                  />
                </div>
              ))}
            </div>
          </div>
        ))}

        {error && <p className="text-sm text-red-400">{error}</p>}
        {saved && !error && <p className="text-sm text-emerald-400">Saved.</p>}

        <button
          type="submit"
          disabled={updateParams.isPending}
          className="rounded bg-blue-600 px-6 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
        >
          {updateParams.isPending ? "Saving..." : "Save changes"}
        </button>
      </form>

      <h2 className="mb-3 text-lg font-semibold text-white">Breaker history</h2>
      {history && history.length > 0 ? (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-500">
              <th className="py-2">When</th>
              <th className="py-2">Event</th>
              <th className="py-2">Severity</th>
              <th className="py-2">Description</th>
            </tr>
          </thead>
          <tbody>
            {history.map((event, i) => (
              <tr key={i} className="border-b border-slate-900">
                <td className="py-2 text-slate-400">{new Date(event.occurred_at).toLocaleString()}</td>
                <td className="py-2 font-mono text-slate-300">{event.event_type}</td>
                <td className={`py-2 font-semibold ${severityTone(event.severity)}`}>{event.severity}</td>
                <td className="py-2 text-slate-400">{event.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-sm text-slate-500">No risk events recorded yet.</p>
      )}
    </div>
  );
}
