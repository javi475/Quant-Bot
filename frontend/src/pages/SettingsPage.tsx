import { useTrades } from "../api/hooks";

function formatCurrency(value: number | null): string {
  if (value === null) return "—";
  return value.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 });
}

export function SettingsPage() {
  const { data: trades, isLoading } = useTrades();

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-white">Settings</h1>

      <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">Telegram alerts</h2>
          <p className="text-sm text-slate-400">
            Configured via <code className="text-slate-300">TELEGRAM_BOT_TOKEN</code>,{" "}
            <code className="text-slate-300">TELEGRAM_CHAT_ID</code>, and{" "}
            <code className="text-slate-300">TELEGRAM_ALERT_PRIORITY</code> at deployment (DOC 5 §2) — not editable
            from here, since changing the bot token/chat live has no meaningful "preview" step.
          </p>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">Historical data</h2>
          <p className="text-sm text-slate-400">
            A wired-up historical data source (ccxt-backed download into the market_data store) lands with a future
            milestone — the Backtesting page currently uses synthetic sample bars generated in the browser.
          </p>
        </div>
      </div>

      <h2 className="mb-3 text-lg font-semibold text-white">Trade history</h2>
      {isLoading ? (
        <p className="text-sm text-slate-500">Loading...</p>
      ) : (trades ?? []).length === 0 ? (
        <p className="text-sm text-slate-500">No trades recorded yet.</p>
      ) : (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-500">
              <th className="py-2">Asset</th>
              <th className="py-2">Side</th>
              <th className="py-2">Qty</th>
              <th className="py-2">Entry</th>
              <th className="py-2">Exit</th>
              <th className="py-2">P&amp;L</th>
              <th className="py-2">Strategy</th>
            </tr>
          </thead>
          <tbody>
            {(trades ?? []).map((t) => (
              <tr key={t.trade_id} className="border-b border-slate-900">
                <td className="py-2 font-mono text-slate-200">{t.asset}</td>
                <td className="py-2 text-slate-400">{t.side}</td>
                <td className="py-2 text-slate-400">{t.quantity}</td>
                <td className="py-2 text-slate-400">{formatCurrency(t.entry_price)}</td>
                <td className="py-2 text-slate-400">{formatCurrency(t.exit_price)}</td>
                <td className={`py-2 font-semibold ${(t.pnl ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                  {t.pnl === null ? "open" : formatCurrency(t.pnl)}
                </td>
                <td className="py-2 font-mono text-xs text-slate-500">{t.strategy_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
