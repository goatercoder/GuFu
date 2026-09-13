export default function Sparkline({ values, width = 46, height = 16 }: { values: (number | null)[]; width?: number; height?: number }) {
  const vals = values.filter((v): v is number => v !== null && Number.isFinite(v));
  if (vals.length < 2) return <span className="muted">·</span>;
  const max = Math.max(...vals.map(Math.abs), 1e-9);
  const n = values.length;
  const bw = Math.max(1, Math.floor((width - n) / n));
  const mid = height / 2;
  const hasNeg = vals.some((v) => v < 0);
  return (
    <svg width={width} height={height} aria-hidden="true" className="inline-block align-middle">
      {values.map((v, i) => {
        if (v === null) return null;
        const h = Math.max(1, (Math.abs(v) / max) * (hasNeg ? mid : height));
        const x = i * (bw + 1);
        const y = hasNeg ? (v >= 0 ? mid - h : mid) : height - h;
        return <rect key={i} x={x} y={y} width={bw} height={h} fill={v >= 0 ? "var(--good)" : "var(--bad)"} opacity={0.85} />;
      })}
    </svg>
  );
}
