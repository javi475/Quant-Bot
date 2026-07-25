import { useRef, useState } from "react";

import {
  useTelegramSettings,
  useTestTelegram,
  useTestWebhook,
  useTrades,
  useUpdateTelegramSettings,
  useUpdateWebhookSettings,
  useWebhookSettings,
} from "../api/hooks";

function formatCurrency(value: number | null): string {
  if (value === null) return "—";
  return value.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 });
}

const PRIORITIES = ["info", "warning", "serious", "critical"];

export function SettingsPage() {
  const { data: trades, isLoading } = useTrades();

  // ---- Telegram ----
  const { data: telegramSettings, isLoading: tgLoading } = useTelegramSettings();
  const updateTelegram = useUpdateTelegramSettings();
  const testTelegram = useTestTelegram();

  const [botToken, setBotToken] = useState("");
  const [chatId, setChatId] = useState("");
  const [alertPriority, setAlertPriority] = useState("info");
  const [tgSaveStatus, setTgSaveStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const [tgTestStatus, setTgTestStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const tgInit = useRef(false);

  if (telegramSettings && !tgInit.current && !tgLoading) {
    setChatId(telegramSettings.chat_id);
    setAlertPriority(telegramSettings.alert_priority);
    tgInit.current = true;
  }

  async function handleTgSave() {
    setTgSaveStatus(null);
    try {
      await updateTelegram.mutateAsync({ bot_token: botToken, chat_id: chatId, alert_priority: alertPriority });
      setTgSaveStatus({ ok: true, message: "Telegram settings saved." });
    } catch (err: unknown) {
      setTgSaveStatus({ ok: false, message: err instanceof Error ? err.message : "Failed to save" });
    }
  }

  async function handleTgTest() {
    setTgTestStatus(null);
    try {
      const result = await testTelegram.mutateAsync();
      setTgTestStatus({ ok: true, message: result.detail });
    } catch (err: unknown) {
      setTgTestStatus({ ok: false, message: err instanceof Error ? err.message : "Test failed" });
    }
  }

  // ---- TradingView Webhook ----
  const { data: webhookSettings, isLoading: whLoading } = useWebhookSettings();
  const updateWebhook = useUpdateWebhookSettings();
  const testWebhook = useTestWebhook();

  const [webhookSecret, setWebhookSecret] = useState("");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [whSaveStatus, setWhSaveStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const [whTestStatus, setWhTestStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const whInit = useRef(false);

  if (webhookSettings && !whInit.current && !whLoading) {
    setWebhookUrl(webhookSettings.webhook_url);
    whInit.current = true;
  }

  async function handleWhSave() {
    setWhSaveStatus(null);
    try {
      await updateWebhook.mutateAsync({ webhook_secret: webhookSecret, webhook_url: webhookUrl });
      setWhSaveStatus({ ok: true, message: "TradingView webhook settings saved." });
    } catch (err: unknown) {
      setWhSaveStatus({ ok: false, message: err instanceof Error ? err.message : "Failed to save" });
    }
  }

  async function handleWhTest() {
    setWhTestStatus(null);
    try {
      const result = await testWebhook.mutateAsync();
      setWhTestStatus({ ok: true, message: result.detail });
    } catch (err: unknown) {
      setWhTestStatus({ ok: false, message: err instanceof Error ? err.message : "Test failed" });
    }
  }

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-white">Settings</h1>

      <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-2">
        {/* Telegram alerts card */}
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
            Telegram alerts
          </h2>

          {telegramSettings?.bot_token_set && (
            <p className="mb-3 text-xs text-slate-500">
              Current token: <code className="text-slate-400">{telegramSettings.bot_token_masked}</code>
            </p>
          )}

          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-slate-400">Bot Token</label>
              <input
                type="password"
                placeholder="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
                value={botToken}
                onChange={(e) => setBotToken(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400">Chat ID</label>
              <input
                type="text"
                placeholder="-1001234567890"
                value={chatId}
                onChange={(e) => setChatId(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400">Minimum Alert Priority</label>
              <select
                value={alertPriority}
                onChange={(e) => setAlertPriority(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:border-emerald-500 focus:outline-none"
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p.charAt(0).toUpperCase() + p.slice(1)}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-slate-500">
                Only alerts at or above this priority are sent. Critical alerts always send.
              </p>
            </div>

            {tgSaveStatus && (
              <p className={`text-xs ${tgSaveStatus.ok ? "text-emerald-400" : "text-red-400"}`}>
                {tgSaveStatus.message}
              </p>
            )}
            {tgTestStatus && (
              <p className={`text-xs ${tgTestStatus.ok ? "text-emerald-400" : "text-red-400"}`}>
                {tgTestStatus.message}
              </p>
            )}

            <div className="flex gap-2">
              <button
                onClick={handleTgSave}
                disabled={updateTelegram.isPending}
                className="rounded bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
              >
                {updateTelegram.isPending ? "Saving…" : "Save"}
              </button>
              <button
                onClick={handleTgTest}
                disabled={testTelegram.isPending || !botToken || !chatId}
                className="rounded border border-slate-600 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800 disabled:opacity-50"
              >
                {testTelegram.isPending ? "Sending…" : "Send Test"}
              </button>
            </div>
          </div>
        </div>

        {/* TradingView webhook card */}
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
            TradingView webhook
          </h2>

          {webhookSettings?.webhook_secret_set && (
            <p className="mb-3 text-xs text-slate-500">
              Current secret: <code className="text-slate-400">{webhookSettings.webhook_secret_masked}</code>
            </p>
          )}

          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-slate-400">Webhook Secret</label>
              <input
                type="password"
                placeholder="ate-smp-webhook-secret-change-in-production"
                value={webhookSecret}
                onChange={(e) => setWebhookSecret(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
              />
              <p className="mt-1 text-xs text-slate-500">
                Used to sign alert payloads via HMAC-SHA256. Must match the <code>WEBHOOK_SECRET</code> env var
                the webhook receiver process was started with, and the "Secret" field in your TradingView alert.
              </p>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400">Webhook Receiver URL</label>
              <input
                type="text"
                placeholder="https://your-server.com:8080"
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
              />
              <p className="mt-1 text-xs text-slate-500">
                The public URL where the webhook receiver is listening. This is the URL you paste into
                TradingView's "Alert → Webhook URL" field.
              </p>
            </div>

            <div className="rounded border border-slate-700 bg-slate-950 p-3">
              <h3 className="mb-1 text-xs font-semibold text-slate-400">Alert payload format</h3>
              <pre className="overflow-x-auto text-xs text-slate-500">
{`{
  "strategy_id": "strat_1",
  "asset": "BTC/USD",
  "direction": "long",
  "strength": 1.0
}`}
              </pre>
              <p className="mt-1 text-xs text-slate-500">
                Paste this JSON template into your TradingView alert's "Message" field. Direction can be{" "}
                <code>long</code>, <code>short</code>, <code>exit_long</code>, <code>exit_short</code>, or{" "}
                <code>flatten</code>.
              </p>
            </div>

            {whSaveStatus && (
              <p className={`text-xs ${whSaveStatus.ok ? "text-emerald-400" : "text-red-400"}`}>
                {whSaveStatus.message}
              </p>
            )}
            {whTestStatus && (
              <p className={`text-xs ${whTestStatus.ok ? "text-emerald-400" : "text-red-400"}`}>
                {whTestStatus.message}
              </p>
            )}

            <div className="flex gap-2">
              <button
                onClick={handleWhSave}
                disabled={updateWebhook.isPending}
                className="rounded bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
              >
                {updateWebhook.isPending ? "Saving…" : "Save"}
              </button>
              <button
                onClick={handleWhTest}
                disabled={testWebhook.isPending || !webhookSecret || !webhookUrl}
                className="rounded border border-slate-600 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800 disabled:opacity-50"
              >
                {testWebhook.isPending ? "Testing…" : "Send Test Signal"}
              </button>
            </div>
          </div>
        </div>

        {/* Historical data card */}
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
