export default function StatTile({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "up" | "down" }) {
  return (
    <div className="card py-3">
      <div className="text-xs uppercase tracking-wide muted">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${tone ?? ""}`}>{value}</div>
      {sub && <div className="text-xs text-2 mt-0.5">{sub}</div>}
    </div>
  );
}
