export function StatTile({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "good" | "bad" | "warn";
}) {
  const toneClasses = {
    default: "text-slate-100",
    good: "text-emerald-400",
    bad: "text-red-400",
    warn: "text-amber-400",
  }[tone];

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${toneClasses}`}>{value}</div>
    </div>
  );
}
