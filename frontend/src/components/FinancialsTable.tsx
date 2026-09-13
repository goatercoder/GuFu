import type { Period } from "../api/types";

type RowDef = { key: string; label: string; kind: "money" | "pershare" | "shares" | "pct"; compute?: (v: Record<string, number>, prev?: Record<string, number>) => number | null };

const GROUPS: { title: string; rows: RowDef[] }[] = [
  { title: "Income Statement", rows: [
    { key: "revenue", label: "Revenue", kind: "money" }, { key: "cost_of_revenue", label: "Cost of Revenue", kind: "money" },
    { key: "gross_profit", label: "Gross Profit", kind: "money" }, { key: "rnd", label: "R&D", kind: "money" },
    { key: "sga", label: "SG&A", kind: "money" }, { key: "dna", label: "Depreciation & Amortization", kind: "money" },
    { key: "operating_income", label: "Operating Income", kind: "money" }, { key: "ebitda", label: "EBITDA", kind: "money" },
    { key: "interest_expense", label: "Interest Expense", kind: "money" }, { key: "pretax_income", label: "Pretax Income", kind: "money" },
    { key: "tax_expense", label: "Income Tax", kind: "money" }, { key: "net_income", label: "Net Income", kind: "money" },
  ] },
  { title: "Balance Sheet", rows: [
    { key: "cash", label: "Cash & Equivalents", kind: "money" }, { key: "short_term_investments", label: "Short-term Investments", kind: "money" },
    { key: "receivables", label: "Receivables", kind: "money" }, { key: "inventory", label: "Inventory", kind: "money" },
    { key: "current_assets", label: "Total Current Assets", kind: "money" }, { key: "ppe_net", label: "PP&E (net)", kind: "money" },
    { key: "goodwill", label: "Goodwill", kind: "money" }, { key: "intangibles", label: "Intangibles", kind: "money" },
    { key: "total_assets", label: "Total Assets", kind: "money" }, { key: "current_liabilities", label: "Total Current Liabilities", kind: "money" },
    { key: "long_term_debt", label: "Long-term Debt", kind: "money" }, { key: "total_debt", label: "Total Debt", kind: "money" },
    { key: "total_liabilities", label: "Total Liabilities", kind: "money" }, { key: "retained_earnings", label: "Retained Earnings", kind: "money" },
    { key: "equity", label: "Shareholders' Equity", kind: "money" }, { key: "working_capital", label: "Working Capital", kind: "money" },
    { key: "net_debt", label: "Net Debt", kind: "money" },
  ] },
  { title: "Cash Flow", rows: [
    { key: "ocf", label: "Operating Cash Flow", kind: "money" }, { key: "capex", label: "Capital Expenditure", kind: "money" },
    { key: "fcf", label: "Free Cash Flow", kind: "money" }, { key: "dividends_paid", label: "Dividends Paid", kind: "money" },
    { key: "buybacks", label: "Share Buybacks", kind: "money" },
  ] },
  { title: "Per Share", rows: [
    { key: "eps_diluted", label: "EPS (diluted)", kind: "pershare" }, { key: "dps", label: "Dividends / Share", kind: "pershare" },
    { key: "bvps", label: "Book Value / Share", kind: "pershare" }, { key: "fcf_per_share", label: "FCF / Share", kind: "pershare" },
    { key: "shares_diluted", label: "Diluted Shares (M)", kind: "shares" }, { key: "shares_outstanding", label: "Shares Outstanding (M)", kind: "shares" },
  ] },
  { title: "Ratios", rows: [
    { key: "_gm", label: "Gross Margin", kind: "pct", compute: (v) => ratio(v.gross_profit, v.revenue) },
    { key: "_om", label: "Operating Margin", kind: "pct", compute: (v) => ratio(v.operating_income, v.revenue) },
    { key: "_nm", label: "Net Margin", kind: "pct", compute: (v) => ratio(v.net_income, v.revenue) },
    { key: "_roe", label: "Return on Equity", kind: "pct", compute: (v) => (v.equity > 0 ? ratio(v.net_income, v.equity) : null) },
    { key: "_roa", label: "Return on Assets", kind: "pct", compute: (v) => ratio(v.net_income, v.total_assets) },
    { key: "_de", label: "Debt / Equity", kind: "pct", compute: (v) => (v.equity > 0 ? ratio(v.total_debt, v.equity) : null) },
    { key: "_payout", label: "Payout Ratio", kind: "pct", compute: (v) => (v.eps_diluted > 0 && v.dps !== undefined ? ratio(v.dps, v.eps_diluted) : null) },
    { key: "_rg", label: "Revenue Growth", kind: "pct", compute: (v, prev) => (prev && prev.revenue > 0 && v.revenue !== undefined ? v.revenue / prev.revenue - 1 : null) },
    { key: "_eg", label: "EPS Growth", kind: "pct", compute: (v, prev) => (prev && prev.eps_diluted > 0 && v.eps_diluted !== undefined && v.eps_diluted > 0 ? v.eps_diluted / prev.eps_diluted - 1 : null) },
  ] },
];

function ratio(a: number | undefined, b: number | undefined): number | null {
  if (a === undefined || b === undefined || !b) return null;
  return a / b;
}

export function fmtCell(kind: RowDef["kind"], v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  const neg = v < 0;
  let s: string;
  if (kind === "money" || kind === "shares") s = (Math.abs(v) / 1e6).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  else if (kind === "pershare") s = Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  else s = (Math.abs(v) * 100).toFixed(1) + "%";
  return neg ? `(${s})` : s;
}

function sourceTitle(p: Period, key: string): string | undefined {
  if (!p.legacy) return p.filed ? `${p.form} · period ending ${p.end} · filed ${p.filed}` : undefined;
  const s = p.source;
  if (!s) return "Parsed from an older 10-K filing";
  const method = s.fields?.[key];
  const how = method ? (method.startsWith("summary") ? "Selected Financial Data table" : method.startsWith("income") ? "income statement" : method.startsWith("balance") ? "balance sheet" : method.startsWith("cashflow") ? "cash-flow statement" : method) : "older filing";
  return `From the ${s.form} for FY${s.filing_fy ?? "?"} (${how}), filed ${s.filed}. Click the year header to open the filing.`;
}

export default function FinancialsTable({ periods, freq, windowFrom, windowTo }: { periods: Period[]; freq: "annual" | "quarterly"; windowFrom?: number; windowTo?: number }) {
  let cols: { label: string; p: Period | null; fy: number }[];
  if (freq === "annual") {
    const byFy = new Map(periods.map((p) => [p.fy, p]));
    const to = windowTo ?? (periods.length ? periods[periods.length - 1].fy : new Date().getFullYear());
    const from = windowFrom ?? to - 29;
    cols = [];
    for (let fy = from; fy <= to; fy++) cols.push({ label: `FY${fy}`, p: byFy.get(fy) ?? null, fy });
  } else {
    cols = periods.slice(-40).map((p) => ({ label: `Q${p.fq} '${String(p.fy).slice(2)}`, p, fy: p.fy }));
  }
  const rowsWithData = (r: RowDef) => cols.some((c) => c.p && (r.compute ? r.compute(c.p.v) !== null : c.p.v[r.key] !== undefined));
  return (
    <div className="overflow-x-auto" style={{ maxHeight: "70vh", overflowY: "auto" }}>
      <table className="data fin-table" data-testid="financials-table">
        <thead>
          <tr>
            <th className="sticky-col">Fiscal year</th>
            {cols.map((c) => (
              <th key={c.label} className="num" title={c.p?.legacy && c.p.source ? `Parsed from the ${c.p.source.form} filed ${c.p.source.filed}` : c.p ? `${c.p.form} filed ${c.p.filed ?? ""}` : "No data"}>
                {c.p?.legacy && c.p.source ? <a href={c.p.source.url} target="_blank" rel="noreferrer" className="hover:underline">{c.label}<span className="legacy-tag" aria-label="from an older 10-K filing">10-K</span></a> : c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {GROUPS.map((g) => {
            const rows = g.rows.filter(rowsWithData);
            if (!rows.length) return null;
            return [
              <tr key={g.title} className="group-row"><td className="sticky-col font-semibold" colSpan={cols.length + 1}>{g.title}</td></tr>,
              ...rows.map((r) => (
                <tr key={r.key}>
                  <td className="sticky-col">{r.label}</td>
                  {cols.map((c, i) => {
                    const p = c.p;
                    if (!p) return <td key={c.label} className="num muted">–</td>;
                    const prev = i > 0 ? cols[i - 1].p?.v : undefined;
                    const v = r.compute ? r.compute(p.v, prev) : p.v[r.key];
                    const derived = !r.compute && p.derived.includes(r.key) && !p.legacy;
                    return (
                      <td key={c.label} className={`num ${p.legacy ? "legacy-cell" : ""} ${derived ? "text-2" : ""}`} title={r.compute ? undefined : sourceTitle(p, r.key)}>
                        {fmtCell(r.kind, v)}
                      </td>
                    );
                  })}
                </tr>
              )),
            ];
          })}
        </tbody>
      </table>
    </div>
  );
}

export function periodsToCsv(periods: Period[], freq: "annual" | "quarterly"): string {
  const header = ["metric", ...periods.map((p) => (freq === "annual" ? `FY${p.fy}` : `Q${p.fq} FY${p.fy}`))];
  const lines = [header.join(",")];
  lines.push(["source", ...periods.map((p) => (p.legacy ? `"${p.source?.form ?? "10-K"} filed ${p.source?.filed ?? ""}"` : `"${p.form} filed ${p.filed ?? ""}"`))].join(","));
  for (const g of GROUPS) {
    for (const r of g.rows) {
      if (r.compute) continue;
      const vals = periods.map((p) => (p.v[r.key] === undefined ? "" : String(p.v[r.key])));
      if (vals.every((v) => v === "")) continue;
      lines.push([`"${r.label}"`, ...vals].join(","));
    }
  }
  return lines.join("\n");
}
