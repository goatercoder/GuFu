import { useState } from "react";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { usePrices } from "../api/client";
import { MONTHS, fmtCompact, fmtPct, fmtPrice } from "../lib/format";

const RANGES = ["1m", "3m", "6m", "ytd", "1y", "5y", "10y", "max"] as const;

export default function PriceChart({ ticker, fairValue }: { ticker: string; fairValue?: number | null }) {
  const [range, setRange] = useState<string>("1y");
  const { data, isLoading, error } = usePrices(ticker, range);
  const pts = data?.points ?? [];
  const first = pts[0]?.c, last = pts[pts.length - 1]?.c;
  const chg = first && last ? last / first - 1 : null;
  const up = (chg ?? 0) >= 0;
  const stroke = up ? "var(--good)" : "var(--bad)";
  const tickFmt = (d: string) => {
    const [y, m, day] = d.split("-");
    const mon = MONTHS[parseInt(m, 10) - 1] ?? m;
    if (range === "1m" || range === "3m") return `${mon} ${parseInt(day, 10)}`;
    if (range === "6m" || range === "ytd" || range === "1y" || range === "2y") return `${mon} '${y.slice(2)}`;
    return y;
  };

  return (
    <div className="card" data-testid="price-chart">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
        <div>
          <h3 className="font-semibold inline">Stock price</h3>
          {chg !== null && <span className={`ml-3 text-sm font-semibold tnum ${up ? "up" : "down"}`}>{fmtPct(chg, 2, true)} over {range.toUpperCase()}</span>}
        </div>
        <div className="flex gap-1 flex-wrap">
          {RANGES.map((r) => <button key={r} className={`btn ${range === r ? "btn-active" : ""}`} onClick={() => setRange(r)}>{r.toUpperCase()}</button>)}
        </div>
      </div>
      <div style={{ height: 300 }}>
        {isLoading ? <div className="skeleton h-full" /> : error ? <div className="muted text-sm p-4">Price history unavailable: {(error as Error).message}</div> : (
          <ResponsiveContainer>
            <AreaChart data={pts} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={`px-${ticker}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={stroke} stopOpacity={0.25} />
                  <stop offset="100%" stopColor={stroke} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="var(--grid)" />
              <XAxis dataKey="d" tickFormatter={tickFmt} minTickGap={48} tick={{ fill: "var(--muted)", fontSize: 11 }} axisLine={{ stroke: "var(--grid)" }} tickLine={false} />
              <YAxis domain={["auto", "auto"]} tickFormatter={(v) => `$${fmtCompact(v, v >= 1000 ? 1 : 0)}`} width={60} tick={{ fill: "var(--muted)", fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip cursor={{ stroke: "var(--muted)", strokeDasharray: "3 3" }} content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const p = payload[0].payload as { d: string; c: number; v: number };
                return <div className="viz-tip"><div className="font-semibold">{p.d}</div><div>Close {fmtPrice(p.c)}</div><div className="muted">Volume {fmtCompact(p.v, 1)}</div></div>;
              }} />
              {fairValue && <ReferenceLine y={fairValue} stroke="var(--brand)" strokeDasharray="4 4" label={{ value: `DCF ${fmtPrice(fairValue, 0)}`, position: "insideTopRight", fill: "var(--brand)", fontSize: 11 }} />}
              <Area type="monotone" dataKey="c" stroke={stroke} strokeWidth={2} fill={`url(#px-${ticker})`} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)" }} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
      <div className="text-xs muted mt-1">Daily close · {data?.source ?? "Yahoo Finance"}{data?.first_date ? ` · history from ${data.first_date}` : ""}{fairValue ? " · dashed line = DCF fair value (earnings)" : ""}</div>
    </div>
  );
}
