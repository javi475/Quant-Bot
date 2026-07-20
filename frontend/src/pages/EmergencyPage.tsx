import { useState } from "react";

import { useFlatten, useHalt, useKillSwitch } from "../api/hooks";
import { ApiError } from "../api/client";

interface ActionButtonProps {
  label: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => Promise<unknown>;
  tone: "amber" | "orange" | "red";
}

const TONE_CLASSES: Record<ActionButtonProps["tone"], string> = {
  amber: "bg-amber-700 hover:bg-amber-600",
  orange: "bg-orange-700 hover:bg-orange-600",
  red: "bg-red-800 hover:bg-red-700",
};

function ActionCard({ label, description, confirmLabel, onConfirm, tone }: ActionButtonProps) {
  const [armed, setArmed] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleClick() {
    if (!armed) {
      setArmed(true);
      setStatus(null);
      return;
    }
    setBusy(true);
    try {
      await onConfirm();
      setStatus("Done.");
    } catch (err) {
      setStatus(err instanceof ApiError ? `Failed: ${err.message}` : "Failed: unknown error");
    } finally {
      setBusy(false);
      setArmed(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-5">
      <h3 className="text-lg font-semibold text-white">{label}</h3>
      <p className="mb-4 mt-1 text-sm text-slate-400">{description}</p>
      <button
        type="button"
        disabled={busy}
        onClick={handleClick}
        className={`w-full rounded px-4 py-2 text-sm font-bold text-white disabled:opacity-50 ${TONE_CLASSES[tone]}`}
      >
        {busy ? "Working..." : armed ? confirmLabel : label}
      </button>
      {armed && !busy && (
        <button
          type="button"
          onClick={() => setArmed(false)}
          className="mt-2 w-full rounded px-4 py-1.5 text-xs text-slate-400 hover:text-slate-200"
        >
          Cancel
        </button>
      )}
      {status && <p className="mt-3 text-sm text-slate-300">{status}</p>}
    </div>
  );
}

export function EmergencyPage() {
  const halt = useHalt();
  const flatten = useFlatten();
  const killSwitch = useKillSwitch();

  return (
    <div>
      <h1 className="mb-2 text-2xl font-bold text-white">Emergency Controls</h1>
      <p className="mb-6 text-sm text-slate-400">
        Every action below requires a second click to confirm. These affect the live Engine immediately.
      </p>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <ActionCard
          label="Halt"
          description="Stops new entries. Existing positions stay open and continue to be monitored."
          confirmLabel="Click again to confirm HALT"
          tone="amber"
          onConfirm={() => halt.mutateAsync()}
        />
        <ActionCard
          label="Flatten"
          description="Market-closes every open position across every connector, right now."
          confirmLabel="Click again to confirm FLATTEN"
          tone="orange"
          onConfirm={() => flatten.mutateAsync()}
        />
        <ActionCard
          label="Kill Switch"
          description="Flattens everything, disables every strategy, and halts the Engine. The most severe control here."
          confirmLabel="Click again to confirm KILL SWITCH"
          tone="red"
          onConfirm={() => killSwitch.mutateAsync()}
        />
      </div>
    </div>
  );
}
