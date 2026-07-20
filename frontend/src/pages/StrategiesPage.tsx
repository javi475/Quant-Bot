import { useState } from "react";

import {
  useActivateVersion,
  useCreateStrategy,
  useStrategies,
  useStrategyVersions,
  useUploadVersion,
} from "../api/hooks";
import { ApiError } from "../api/client";

const ASSET_CLASSES = ["crypto", "futures", "options", "forex", "stocks", "prediction_markets"];

const SAMPLE_SOURCE = `from ate_smp import StrategyBase, Direction, Signal

class MyStrategy(StrategyBase):
    def initialize(self, config):
        self.config = config

    def on_bar(self, bar):
        return []

    def on_tick(self, tick):
        return []

    def on_fill(self, fill):
        pass

    def get_parameters_schema(self):
        return []

    def get_win_probability(self):
        return 0.55

    def get_win_loss_ratio(self):
        return 1.5

    def get_state(self):
        return {}

    def set_state(self, state):
        pass
`;

function CreateStrategyForm() {
  const createStrategy = useCreateStrategy();
  const [name, setName] = useState("");
  const [assetClass, setAssetClass] = useState(ASSET_CLASSES[0]);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await createStrategy.mutateAsync({ name, asset_class: assetClass, tags: [] });
      setName("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create strategy");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mb-8 flex items-end gap-3 rounded-lg border border-slate-800 bg-slate-900 p-4">
      <div className="flex-1">
        <label className="mb-1 block text-xs font-medium text-slate-400" htmlFor="strategy-name">
          New strategy name
        </label>
        <input
          id="strategy-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-blue-500 focus:outline-none"
        />
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium text-slate-400" htmlFor="asset-class">
          Asset class
        </label>
        <select
          id="asset-class"
          value={assetClass}
          onChange={(e) => setAssetClass(e.target.value)}
          className="rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-blue-500 focus:outline-none"
        >
          {ASSET_CLASSES.map((ac) => (
            <option key={ac} value={ac}>
              {ac}
            </option>
          ))}
        </select>
      </div>
      <button
        type="submit"
        disabled={createStrategy.isPending}
        className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
      >
        Create
      </button>
      {error && <p className="text-sm text-red-400">{error}</p>}
    </form>
  );
}

function VersionsPanel({ strategyId }: { strategyId: string }) {
  const { data: versions, isLoading } = useStrategyVersions(strategyId);
  const uploadVersion = useUploadVersion(strategyId);
  const activateVersion = useActivateVersion(strategyId);
  const [sourceCode, setSourceCode] = useState(SAMPLE_SOURCE);
  const [className, setClassName] = useState("MyStrategy");
  const [error, setError] = useState<string | null>(null);

  async function handleUpload(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await uploadVersion.mutateAsync({ source_code: sourceCode, class_name: className });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload rejected");
    }
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-5">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">Versions</h3>
      {isLoading ? (
        <p className="text-sm text-slate-500">Loading...</p>
      ) : (
        <table className="mb-5 w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-500">
              <th className="py-2">Version</th>
              <th className="py-2">Class</th>
              <th className="py-2">Checksum</th>
              <th className="py-2">Status</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody>
            {(versions ?? []).map((v) => (
              <tr key={v.id} className="border-b border-slate-900">
                <td className="py-2 font-mono text-slate-300">{v.version}</td>
                <td className="py-2 text-slate-400">{v.class_name}</td>
                <td className="py-2 font-mono text-xs text-slate-600">{v.checksum_sha256.slice(0, 12)}...</td>
                <td className="py-2">
                  {v.is_active ? (
                    <span className="rounded bg-emerald-900/40 px-2 py-0.5 text-xs text-emerald-400">Active</span>
                  ) : (
                    <span className="text-xs text-slate-500">Inactive</span>
                  )}
                </td>
                <td className="py-2 text-right">
                  {!v.is_active && (
                    <button
                      type="button"
                      onClick={() => activateVersion.mutate(v.version)}
                      className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
                    >
                      Activate / rollback
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {versions?.length === 0 && (
              <tr>
                <td colSpan={5} className="py-3 text-center text-sm text-slate-500">
                  No versions uploaded yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}

      <form onSubmit={handleUpload}>
        <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">Upload new version</h3>
        <label className="mb-1 block text-xs font-medium text-slate-400" htmlFor="class-name">
          Strategy class name
        </label>
        <input
          id="class-name"
          value={className}
          onChange={(e) => setClassName(e.target.value)}
          className="mb-3 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 focus:border-blue-500 focus:outline-none"
        />
        <label className="mb-1 block text-xs font-medium text-slate-400" htmlFor="source-code">
          Source code
        </label>
        <textarea
          id="source-code"
          value={sourceCode}
          onChange={(e) => setSourceCode(e.target.value)}
          rows={14}
          spellCheck={false}
          className="mb-3 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100 focus:border-blue-500 focus:outline-none"
        />
        {error && <p className="mb-3 text-sm text-red-400">{error}</p>}
        <button
          type="submit"
          disabled={uploadVersion.isPending}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
        >
          {uploadVersion.isPending ? "Validating..." : "Upload version"}
        </button>
      </form>
    </div>
  );
}

export function StrategiesPage() {
  const { data: strategies, isLoading } = useStrategies();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-white">Strategies</h1>
      <CreateStrategyForm />

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <div>
          <h2 className="mb-3 text-lg font-semibold text-white">All strategies</h2>
          {isLoading ? (
            <p className="text-sm text-slate-500">Loading...</p>
          ) : (
            <div className="space-y-2">
              {(strategies ?? []).map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setSelectedId(s.id)}
                  className={`block w-full rounded-lg border p-3 text-left text-sm transition-colors ${
                    selectedId === s.id
                      ? "border-blue-600 bg-slate-800"
                      : "border-slate-800 bg-slate-900 hover:bg-slate-800/60"
                  }`}
                >
                  <div className="font-semibold text-slate-100">{s.name}</div>
                  <div className="text-xs text-slate-500">
                    {s.asset_class} · {s.state}
                    {s.tags.length > 0 ? ` · ${s.tags.join(", ")}` : ""}
                  </div>
                </button>
              ))}
              {strategies?.length === 0 && <p className="text-sm text-slate-500">No strategies yet — create one above.</p>}
            </div>
          )}
        </div>

        <div>
          <h2 className="mb-3 text-lg font-semibold text-white">Version management</h2>
          {selectedId ? (
            <VersionsPanel strategyId={selectedId} />
          ) : (
            <p className="text-sm text-slate-500">Select a strategy on the left to manage its versions.</p>
          )}
        </div>
      </div>
    </div>
  );
}
