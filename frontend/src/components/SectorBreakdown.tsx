import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { HomeResponse } from "../api/types";
import { fmtMoney, fmtPct, fmtRatio } from "../lib/format";

export default function SectorBreakdown({ sectors }: { sectors: HomeResponse["sectors"] }) {
  const data = sectors.map((s) => ({ ...s, short: s.sector.replace("Information Technology", "Info Tech").replace("Communication Services", "Comm Services").replace("Consumer Discretionary", "Cons Discretionary").replace("Consumer Staples", "Cons Staples") }));
  return (
    <div className="card">
      <h3 className="font-semibold mb-1">Market cap by sector</h3>
      <div className="text-xs muted mb-2">Sum of constituent market caps · hover for median P/E and today's average move</div>
      <div style={{ height: 330 }}>
        <ResponsiveContainer>
          <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24, top: 4, bottom: 4 }} barCategoryGap={6}>
            <CartesianGrid horizontal={false} stroke="var(--grid)" />
            <XAxis type="number" tickFormatter={(v) => fmtMoney(v, 0)} tick={{ fill: "var(--muted)", fontSize: 11 }} axisLine={{ stroke: "var(--grid)" }} tickLine={false} />
            <YAxis type="category" dataKey="short" width={120} tick={{ fill: "var(--text-2)", fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip cursor={{ fill: "var(--neutral-bg)", opacity: 0.5 }} content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0].payload as HomeResponse["sectors"][number];
              return (
                <div className="viz-tip">
                  <div className="font-semibold">{d.sector}</div>
                  <div>{d.count} companies · {fmtMoney(d.market_cap)}</div>
                  <div>Median P/E {fmtRatio(d.median_pe, 1)} · Avg move {fmtPct(d.avg_change_pct, 2, true)}</div>
                </div>
              );
            }} />
            <Bar dataKey="market_cap" radius={[0, 4, 4, 0]} maxBarSize={18}>
              {data.map((d) => <Cell key={d.sector} fill="var(--brand)" />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
