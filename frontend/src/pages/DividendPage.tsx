import { useOutletContext } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useFinancials } from "../api/client";
import MetricTable from "../components/MetricTable";
import { colLabel, fmtDense, fmtYoy } from "../lib/fin";
import { fmtMoney } from "../lib/format";
import type { CompanyContext } from "./CompanyShell";

export default function DividendPage() {
  const { ticker: t, data } = useOutletContext<CompanyContext>();
  const fin = useFinancials(t, "annual");
  const periods = (fin.data?.periods ?? []).slice(-30);
  const dps = (v: Record<string, number>) => v.dps ?? v.dps_derived ?? null;
  const rows = periods.map((p, i) => {
    const d = dps(p.v);
    const prev = i > 0 ? dps(periods[i - 1].v) : null;
    return { label: colLabel(p), key: p.key, dps: d, growth: fmtYoy(d, prev), payout: d !== null && p.v.eps_diluted > 0 ? d / p.v.eps_diluted : null, yieldPct: d !== null && p.px ? d / p.px : null, paid: p.v.dividends_paid ?? null, buybacks: p.v.buybacks ?? null };
  });
  const dividend = data.groups.find((g) => g.group === "dividend");
  const pays = rows.some((r) => (r.dps ?? 0) > 0);
  return (
    <div className="space-y-4" data-testid="dividend-page">
      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 card">
          <h3 className="font-semibold mb-1">Dividends per share</h3>
          <div className="text-xs muted mb-2">{pays ? "Declared per fiscal year" : "This company has not paid a common dividend in the covered period."}</div>
          <div style={{ height: 260 }}>
            <ResponsiveContainer>
              <BarChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--grid)" />
                <XAxis dataKey="label" tick={{ fill: "var(--muted)", fontSize: 11 }} axisLine={{ stroke: "var(--grid)" }} tickLine={false} interval={Math.max(0, Math.floor(rows.length / 10))} />
                <YAxis tick={{ fill: "var(--muted)", fontSize: 11 }} axisLine={false} tickLine={false} width={44} tickFormatter={(v) => `$${Number(v).toFixed(2)}`} />
                <Tooltip cursor={{ fill: "var(--neutral-bg)", opacity: 0.5 }} contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} formatter={(v) => (typeof v === "number" ? `$${v.toFixed(2)}` : "-")} />
                <Bar dataKey="dps" name="Dividend / share" fill="var(--brand)" radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        {dividend && <MetricTable group={dividend} />}
      </div>
      <div className="card">
        <h3 className="font-semibold mb-2">Dividend history</h3>
        <div className="overflow-x-auto">
          <table className="data">
            <thead><tr><th>Fiscal year</th><th className="num">Dividend / share</th><th className="num">Growth</th><th className="num">Payout ratio</th><th className="num">Yield at year-end</th><th className="num">Dividends paid</th><th className="num">Buybacks</th></tr></thead>
            <tbody>
              {[...rows].reverse().map((r) => (
                <tr key={r.key}><td>{r.label}</td><td className="num">{r.dps === null ? "-" : `$${r.dps.toFixed(2)}`}</td><td className="num">{r.growth}</td><td className="num">{fmtDense(r.payout, "pct", 0)}{r.payout !== null ? "%" : ""}</td><td className="num">{fmtDense(r.yieldPct, "pct", 0)}{r.yieldPct !== null ? "%" : ""}</td><td className="num">{fmtMoney(r.paid)}</td><td className="num">{fmtMoney(r.buybacks)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
