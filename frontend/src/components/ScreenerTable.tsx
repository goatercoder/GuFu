import { Link } from "react-router-dom";
import type { MetricDef, ScreenerResponse } from "../api/types";
import { changeClass, fmtMetric, fmtPct, fmtPrice } from "../lib/format";

export default function ScreenerTable({ data, defs, sort, order, onSort }: { data: ScreenerResponse; defs: Record<string, MetricDef>; sort: string; order: string; onSort: (k: string) => void }) {
  const arrow = (k: string) => (sort === k ? (order === "asc" ? " ▲" : " ▼") : "");
  const head = (k: string, label: string, num = true) => (
    <th key={k} className={`${num ? "num" : ""} cursor-pointer select-none hover:underline`} onClick={() => onSort(k)} title={defs[k]?.explanation}>{label}{arrow(k)}</th>
  );
  return (
    <div className="overflow-x-auto">
      <table className="data" data-testid="screener-table">
        <thead>
          <tr>
            {head("ticker", "Ticker", false)}
            {head("name", "Company", false)}
            {head("sector", "Sector", false)}
            {head("price", "Price")}
            {head("change_pct", "Chg")}
            {data.columns.map((c) => head(c, defs[c]?.label ?? c))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => (
            <tr key={r.ticker}>
              <td><Link className="font-semibold hover:underline" to={`/company/${r.ticker}`}>{r.ticker}</Link></td>
              <td className="max-w-[220px] truncate" title={r.name}>{r.name}</td>
              <td className="text-2 whitespace-nowrap">{r.sector}</td>
              <td className="num">{fmtPrice(r.price)}</td>
              <td className={`num ${changeClass(r.change_pct)}`}>{fmtPct(r.change_pct, 2, true)}</td>
              {data.columns.map((c) => <td key={c} className="num">{fmtMetric(defs[c]?.fmt ?? "ratio", r[c] as number | null, defs[c]?.decimals ?? 2)}</td>)}
            </tr>
          ))}
          {data.rows.length === 0 && <tr><td colSpan={5 + data.columns.length} className="muted text-center py-6">No companies match these filters.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
