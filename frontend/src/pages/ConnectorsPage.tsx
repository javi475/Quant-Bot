import { useState } from "react";

import { useConnectors, useCreateConnector, useTestConnector } from "../api/hooks";
import { ApiError } from "../api/client";

const ASSET_CLASSES = ["crypto", "futures", "options", "forex", "stocks", "prediction_markets"];
const CONNECTOR_TYPES = ["paper", "ccxt", "alpaca", "ib", "oanda", "tradingview_webhook"];

function CreateConnectorForm() {
  const createConnector = useCreateConnector();
  const [name, setName] = useState("");
  const [connectorType, setConnectorType] = useState(CONNECTOR_TYPES[0]);
  const [assetClass, setAssetClass] = useState(ASSET_CLASSES[0]);
  const [credentialsJson, setCredentialsJson] = useState("{}");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    let credentials: Record<string, string>;
    try {
      credentials = JSON.parse(credentialsJson) as Record<string, string>;
    } catch {
      setError("Credentials must be valid JSON, e.g. {\"api_key\": \"...\"}");
      return;
    }
    try {
      await createConnector.mutateAsync({ name, connector_type: connectorType, asset_class: assetClass, credentials });
      setName("");
      setCredentialsJson("{}");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create connector");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mb-8 rounded-lg border border-slate-800 bg-slate-900 p-5">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">Add connector</h2>
      <div className="mb-3 grid grid-cols-1 gap-4 md:grid-cols-3">
        <div>
          <label className="mb-1 block text-xs text-slate-500" htmlFor="conn-name">
            Name
          </label>
          <input
            id="conn-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-500" htmlFor="conn-type">
            Type
          </label>
          <select
            id="conn-type"
            value={connectorType}
            onChange={(e) => setConnectorType(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          >
            {CONNECTOR_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-500" htmlFor="conn-asset-class">
            Asset class
          </label>
          <select
            id="conn-asset-class"
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
      </div>

      <label className="mb-1 block text-xs text-slate-500" htmlFor="conn-credentials">
        Credentials (JSON — encrypted at rest, never shown again after saving)
      </label>
      <textarea
        id="conn-credentials"
        value={credentialsJson}
        onChange={(e) => setCredentialsJson(e.target.value)}
        rows={3}
        spellCheck={false}
        className="mb-3 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100"
      />

      {error && <p className="mb-3 text-sm text-red-400">{error}</p>}
      <button
        type="submit"
        disabled={createConnector.isPending}
        className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
      >
        {createConnector.isPending ? "Saving..." : "Add connector"}
      </button>
    </form>
  );
}

function ConnectorRow({ connector }: { connector: { id: string; name: string; connector_type: string; asset_class: string; is_active: boolean } }) {
  const testConnector = useTestConnector();
  const [result, setResult] = useState<string | null>(null);

  async function handleTest() {
    setResult(null);
    try {
      const res = await testConnector.mutateAsync(connector.id);
      setResult(res.status === "ok" ? "Connected OK" : res.detail ?? res.status);
    } catch (err) {
      setResult(err instanceof ApiError ? `Error: ${err.message}` : "Test failed");
    }
  }

  return (
    <tr className="border-b border-slate-900">
      <td className="py-2 font-semibold text-slate-100">{connector.name}</td>
      <td className="py-2 text-slate-400">{connector.connector_type}</td>
      <td className="py-2 text-slate-400">{connector.asset_class}</td>
      <td className="py-2">
        {connector.is_active ? (
          <span className="text-emerald-400">Active</span>
        ) : (
          <span className="text-slate-500">Inactive</span>
        )}
      </td>
      <td className="py-2 text-right">
        <button
          type="button"
          onClick={handleTest}
          disabled={testConnector.isPending}
          className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
        >
          Test connection
        </button>
        {result && <div className="mt-1 text-xs text-slate-400">{result}</div>}
      </td>
    </tr>
  );
}

export function ConnectorsPage() {
  const { data: connectors, isLoading } = useConnectors();

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-white">Connectors</h1>
      <CreateConnectorForm />

      <h2 className="mb-3 text-lg font-semibold text-white">All connectors</h2>
      {isLoading ? (
        <p className="text-sm text-slate-500">Loading...</p>
      ) : (connectors ?? []).length === 0 ? (
        <p className="text-sm text-slate-500">No connectors configured yet.</p>
      ) : (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-500">
              <th className="py-2">Name</th>
              <th className="py-2">Type</th>
              <th className="py-2">Asset class</th>
              <th className="py-2">Status</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody>
            {(connectors ?? []).map((c) => (
              <ConnectorRow key={c.id} connector={c} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
