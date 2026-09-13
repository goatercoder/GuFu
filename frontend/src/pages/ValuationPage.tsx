import { useOutletContext } from "react-router-dom";
import { Line, LineChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { useFinancials } from "../api/client";
import DcfPanel from "../components/DcfPanel";
import MetricTable from "../components/MetricTable";
import PriceChart from "../components/PriceChart";
import { SECTIONS, colLabel, fmtDense } from "../lib/fin";
import type { CompanyContext } from "./CompanyShell";

const RATIO_KEYS = ["px", "pe", "ps", "pb", "pfcf", "ev_ebitda", "yield"];

export default function ValuationPage() {
  const { ticker: t, data } = useOutletContext<CompanyContext>();
  const fin = useFinancials(t, "annual");
  const rows = [...SECTIONS[0].rows, ...SECTIONS[1].rows].filter((r) => RATIO_KEYS.includes(r.key));
  const periods = (fin.data?.periods ?? []).filter((p) => p.px !== null && p.px !== undefined).slice(-20);
  const chart = periods.map((p) => ({ label: colLabel(p), pe: rows.find((r) => r.key === "pe")!.get(p.v, p.px ?? null), ps: rows.find((r) => r.key === "ps")!.get(p.v, p.px ?? null), pb: rows.find((r) => r.key === "pb")!.get(p.v, p.px ?? null) }));
  const valuation = data.groups.find((g) => g.group === "valuation");
  return (
    <div className="space-y-4" data-testid="valuation-page">
      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2"><PriceChart ticker={t} fairValue={data.dcf.eps.value} /></div>
        {valuation && <MetricTable group={valuation} />}
      </div>
      <DcfPanel dcf={data.dcf} price={data.quote.price} graham={data.metrics.graham_number} />
      <div className="card">
        <h3 className="font-semibold mb-1">Historical valuation</h3>
        <div className="text-xs muted mb-2">Ratios at each fiscal year-end using the month-end stock price · last {periods.length} years</div>
        <div style={{ height: 260 }}>
          <ResponsiveContainer>
            <LineChart data={chart} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--grid)" />
              <XAxis dataKey="label" tick={{ fill: "var(--muted)", fontSize: 11 }} axisLine={{ stroke: "var(--grid)" }} tickLine={false} interval={Math.max(0, Math.floor(chart.length / 10))} />
              <YAxis tick={{ fill: "var(--muted)", fontSize: 11 }} axisLine={false} tickLine={false} width={40} />
              <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} formatter={(v) => (typeof v === "number" ? v.toFixed(2) : "-")} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="pe" name="P/E" stroke="var(--brand)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
              <Line type="monotone" dataKey="ps" name="P/S" stroke="var(--brand-2)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
              <Line type="monotone" dataKey="pb" name="P/B" stroke="var(--series-3)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="overflow-x-auto mt-2">
          <table className="fy" style={{ fontSize: 12, width: "100%" }}>
            <thead><tr><th className="lab">Fiscal year-end</th>{periods.map((p) => <th key={p.key} className="num">{colLabel(p)}</th>)}</tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key}><td className="lab">{r.label}</td>{periods.map((p) => { const v = r.get(p.v, p.px ?? null); return <td key={p.key} className={`num ${v !== null && v < 0 ? "neg" : ""}`}>{fmtDense(v, r.kind, 0)}</td>; })}</tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
