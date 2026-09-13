import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useFinancials } from "../api/client";
import type { Period } from "../api/types";
import { fmtCompact, fmtDate, fmtMoney, fmtPrice } from "../lib/format";

const YEARS = 30;

type Pt = { label: string; fy: number; v: number | null; derived: boolean; period: Period | null };

function fmtVal(unit: string, v: number | null): string {
  if (v === null) return "—";
  if (unit === "USD/shares") return fmtPrice(v);
  if (unit === "shares") return fmtCompact(v, 2);
  return fmtMoney(v);
}

export default function FinancialChart({ ticker }: { ticker: string }) {
  const [freq, setFreq] = useState<"annual" | "quarterly">("annual");
  const [field, setField] = useState("revenue");
  const [compare, setCompare] = useState<string>("");
  const { data, isLoading, error } = useFinancials(ticker, freq);
  const fields = data?.fields ?? [];
  const fdef = fields.find((f) => f.key === field) ?? fields[0];
  const cdef = fields.find((f) => f.key === compare);
  const unit = fdef?.unit ?? "USD";
  const isInstant = fdef?.kind === "instant";

  const points: Pt[] = useMemo(() => {
    if (!data) return [];
    const periods = data.periods;
    if (freq === "annual") {
      const lastFy = periods.length ? periods[periods.length - 1].fy : new Date().getFullYear();
      const byFy = new Map(periods.map((p) => [p.fy, p]));
      const out: Pt[] = [];
      for (let fy = lastFy - YEARS + 1; fy <= lastFy; fy++) {
        const p = byFy.get(fy) ?? null;
        out.push({ label: String(fy), fy, v: p?.v[field] ?? null, derived: !!p?.derived.includes(field), period: p });
      }
      return out;
    }
    return periods.slice(-60).map((p) => ({ label: `Q${p.fq} '${String(p.fy).slice(2)}`, fy: p.fy, v: p.v[field] ?? null, derived: p.derived.includes(field), period: p }));
  }, [data, field, freq]);

  const comparePts = useMemo(() => {
    if (!data || !cdef || cdef.unit !== unit) return null;
    const map = new Map(data.periods.map((p) => [freq === "annual" ? String(p.fy) : `Q${p.fq} '${String(p.fy).slice(2)}`, p.v[compare] ?? null]));
    return points.map((pt) => ({ ...pt, c: map.get(pt.label) ?? null }));
  }, [data, cdef, compare, points, freq, unit]);

  const chartData = (comparePts ?? points).map((p) => ({ ...p }));
  const available = points.filter((p) => p.v !== null).length;
  const firstFy = data?.periods[0]?.fy;
  const tickFmt = (v: number) => (unit === "USD/shares" ? `$${fmtCompact(v, 1)}` : fmtCompact(v, 0));
  const hasNeg = chartData.some((p) => (p.v ?? 0) < 0 || ((p as { c?: number | null }).c ?? 0) < 0);

  return (
    <div className="card" data-testid="financial-chart">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
        <div>
          <h3 className="font-semibold inline">{freq === "annual" ? `${YEARS}-year financials` : "Quarterly financials"}</h3>
          <span className="ml-2 text-xs muted">from SEC 10-K / 10-Q XBRL filings</span>
        </div>
        <div className="flex gap-2 flex-wrap items-center">
          <select className="input w-auto" value={field} onChange={(e) => setField(e.target.value)} aria-label="Metric">
            {fields.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
          </select>
          <select className="input w-auto" value={compare} onChange={(e) => setCompare(e.target.value)} aria-label="Compare with">
            <option value="">Compare with…</option>
            {fields.filter((f) => f.key !== field && f.unit === unit).map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
          </select>
          <div className="flex gap-1">
            <button className={`btn ${freq === "annual" ? "btn-active" : ""}`} onClick={() => setFreq("annual")}>Annual</button>
            <button className={`btn ${freq === "quarterly" ? "btn-active" : ""}`} onClick={() => setFreq("quarterly")}>Quarterly</button>
          </div>
        </div>
      </div>
      <div style={{ height: 320 }}>
        {isLoading ? <div className="skeleton h-full" /> : error ? <div className="muted text-sm p-4">Financials unavailable: {(error as Error).message}</div> : (
          <ResponsiveContainer>
            {isInstant && !comparePts ? (
              <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--grid)" />
                <XAxis dataKey="label" interval={freq === "annual" ? 1 : 7} tick={{ fill: "var(--muted)", fontSize: 11 }} axisLine={{ stroke: "var(--grid)" }} tickLine={false} />
                <YAxis tickFormatter={tickFmt} width={64} tick={{ fill: "var(--muted)", fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip content={<Tip unit={unit} label={fdef?.label ?? ""} />} />
                <Line type="monotone" dataKey="v" name={fdef?.label} stroke="var(--brand)" strokeWidth={2} connectNulls dot={{ r: 3, fill: "var(--brand)", strokeWidth: 0 }} activeDot={{ r: 5 }} isAnimationActive={false} />
              </LineChart>
            ) : (
              <BarChart data={chartData} margin={{ top: 8, right: 12, bottom: 0, left: 0 }} barCategoryGap={freq === "annual" ? "25%" : "15%"} barGap={2}>
                <defs>
                  <pattern id="hatch" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
                    <rect width="6" height="6" fill="var(--brand)" opacity="0.35" />
                    <line x1="0" y1="0" x2="0" y2="6" stroke="var(--brand)" strokeWidth="2" />
                  </pattern>
                </defs>
                <CartesianGrid vertical={false} stroke="var(--grid)" />
                <XAxis dataKey="label" interval={freq === "annual" ? 1 : 7} tick={{ fill: "var(--muted)", fontSize: 11 }} axisLine={{ stroke: "var(--grid)" }} tickLine={false} />
                <YAxis tickFormatter={tickFmt} width={64} tick={{ fill: "var(--muted)", fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip cursor={{ fill: "var(--neutral-bg)", opacity: 0.5 }} content={<Tip unit={unit} label={fdef?.label ?? ""} compareLabel={cdef?.label} />} />
                {hasNeg && <ReferenceLine y={0} stroke="var(--muted)" />}
                {comparePts && <Legend wrapperStyle={{ fontSize: 12 }} />}
                <Bar dataKey="v" name={fdef?.label} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false}>
                  {chartData.map((p) => <Cell key={p.label} fill={p.derived ? "url(#hatch)" : "var(--brand)"} />)}
                </Bar>
                {comparePts && <Bar dataKey="c" name={cdef?.label} fill="var(--brand-2)" radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />}
              </BarChart>
            )}
          </ResponsiveContainer>
        )}
      </div>
      <div className="text-xs muted mt-1 flex flex-wrap gap-x-4">
        <span>{available} of {freq === "annual" ? YEARS : points.length} periods have data{firstFy ? ` · earliest fiscal year ${firstFy}` : ""}</span>
        {freq === "quarterly" && <span>Hatched bars: quarter derived from year-to-date figures (Q4 = FY − 9M)</span>}
        <span>SEC structured (XBRL) data begins with fiscal years ending 2009+; earlier years are not available in machine-readable filings.</span>
      </div>
    </div>
  );
}

function Tip({ active, payload, unit, label, compareLabel }: { active?: boolean; payload?: { payload: Pt & { c?: number | null } }[]; unit: string; label: string; compareLabel?: string }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="viz-tip">
      <div className="font-semibold">{p.period ? p.period.label : p.label}</div>
      <div>{label}: <span className="font-semibold">{fmtVal(unit, p.v)}</span>{p.derived && <span className="muted"> (derived)</span>}</div>
      {compareLabel && <div>{compareLabel}: <span className="font-semibold">{fmtVal(unit, p.c ?? null)}</span></div>}
      {p.period ? <div className="muted">{p.period.form} · period end {fmtDate(p.period.end)} · filed {fmtDate(p.period.filed)}</div> : <div className="muted">No filing data for this year</div>}
    </div>
  );
}
