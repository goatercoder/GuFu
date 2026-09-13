/** Row definitions and formatting for the GuruFocus-style 30-Y tables. Values derived client-side from period rows. */
import type { Period } from "../api/types";

export type Kind = "money" | "pershare" | "pct" | "ratio" | "shares" | "price";
export type Cell = number | null;
export interface RowDef { key: string; label: string; kind: Kind; get: (v: Record<string, number>, px: number | null) => Cell; hint?: string }

const g = (v: Record<string, number>, k: string): number | null => (v[k] === undefined || v[k] === null ? null : v[k]);
const div = (a: number | null, b: number | null): Cell => (a === null || b === null || !b ? null : a / b);
const shares = (v: Record<string, number>) => g(v, "shares_diluted") ?? g(v, "shares_outstanding");
const pos = (x: Cell) => (x !== null && x > 0 ? x : null);

export const SECTIONS: { id: string; title: string; rows: RowDef[] }[] = [
  { id: "per-share", title: "Per Share Data", rows: [
    { key: "revenue_ps", label: "Revenue per Share", kind: "pershare", get: (v) => div(g(v, "revenue"), shares(v)) },
    { key: "ebitda_ps", label: "EBITDA per Share", kind: "pershare", get: (v) => div(g(v, "ebitda"), shares(v)) },
    { key: "eps_diluted", label: "Earnings per Share (Diluted)", kind: "pershare", get: (v) => g(v, "eps_diluted") },
    { key: "fcf_ps", label: "Free Cash Flow per Share", kind: "pershare", get: (v) => div(g(v, "fcf"), shares(v)) },
    { key: "ocf_ps", label: "Operating Cash Flow per Share", kind: "pershare", get: (v) => div(g(v, "ocf"), shares(v)) },
    { key: "dps", label: "Dividends per Share", kind: "pershare", get: (v) => g(v, "dps") ?? g(v, "dps_derived") },
    { key: "cash_ps", label: "Cash per Share", kind: "pershare", get: (v) => div(g(v, "cash"), shares(v)) },
    { key: "debt_ps", label: "Total Debt per Share", kind: "pershare", get: (v) => div(g(v, "total_debt"), shares(v)) },
    { key: "bvps", label: "Book Value per Share", kind: "pershare", get: (v) => div(g(v, "equity"), shares(v)) },
    { key: "shares_diluted", label: "Shares Outstanding (Diluted, M)", kind: "shares", get: (v) => shares(v) },
    { key: "px", label: "Month End Stock Price", kind: "price", get: (_v, px) => px },
  ] },
  { id: "ratios", title: "Ratios", rows: [
    { key: "pe", label: "P/E Ratio", kind: "ratio", get: (v, px) => div(px, pos(g(v, "eps_diluted"))) },
    { key: "ps", label: "P/S Ratio", kind: "ratio", get: (v, px) => div(px, pos(div(g(v, "revenue"), shares(v)))) },
    { key: "pb", label: "P/B Ratio", kind: "ratio", get: (v, px) => div(px, pos(div(g(v, "equity"), shares(v)))) },
    { key: "pfcf", label: "P/FCF Ratio", kind: "ratio", get: (v, px) => div(px, pos(div(g(v, "fcf"), shares(v)))) },
    { key: "ev_ebitda", label: "EV-to-EBITDA", kind: "ratio", get: (v, px) => { const s = shares(v); if (px === null || s === null) return null; const ev = px * s + (g(v, "total_debt") ?? 0) - (g(v, "cash") ?? 0); return div(ev, pos(g(v, "ebitda"))); } },
    { key: "yield", label: "Dividend Yield %", kind: "pct", get: (v, px) => div(g(v, "dps") ?? g(v, "dps_derived"), px) },
    { key: "payout", label: "Dividend Payout Ratio", kind: "pct", get: (v) => div(g(v, "dps") ?? g(v, "dps_derived"), pos(g(v, "eps_diluted"))) },
    { key: "gm", label: "Gross Margin %", kind: "pct", get: (v) => div(g(v, "gross_profit"), g(v, "revenue")) },
    { key: "om", label: "Operating Margin %", kind: "pct", get: (v) => div(g(v, "operating_income"), g(v, "revenue")) },
    { key: "nm", label: "Net Margin %", kind: "pct", get: (v) => div(g(v, "net_income"), g(v, "revenue")) },
    { key: "fcfm", label: "FCF Margin %", kind: "pct", get: (v) => div(g(v, "fcf"), g(v, "revenue")) },
    { key: "roe", label: "ROE %", kind: "pct", get: (v) => div(g(v, "net_income"), pos(g(v, "equity"))) },
    { key: "roa", label: "ROA %", kind: "pct", get: (v) => div(g(v, "net_income"), g(v, "total_assets")) },
    { key: "roic", label: "ROIC %", kind: "pct", get: (v) => { const oi = g(v, "operating_income"), eq = g(v, "equity"); if (oi === null || eq === null) return null; const ic = eq + (g(v, "total_debt") ?? 0) - (g(v, "cash") ?? 0); return ic > 0 ? (oi * 0.79) / ic : null; } },
    { key: "cr", label: "Current Ratio", kind: "ratio", get: (v) => div(g(v, "current_assets"), g(v, "current_liabilities")) },
    { key: "de", label: "Debt-to-Equity", kind: "ratio", get: (v) => div(g(v, "total_debt"), pos(g(v, "equity"))) },
    { key: "ea", label: "Equity-to-Asset", kind: "ratio", get: (v) => div(g(v, "equity"), g(v, "total_assets")) },
    { key: "ic", label: "Interest Coverage", kind: "ratio", get: (v) => div(g(v, "operating_income"), pos(g(v, "interest_expense") !== null ? Math.abs(g(v, "interest_expense")!) : null)) },
    { key: "at", label: "Asset Turnover", kind: "ratio", get: (v) => div(g(v, "revenue"), g(v, "total_assets")) },
  ] },
  { id: "income", title: "Income Statement", rows: [
    { key: "revenue", label: "Revenue", kind: "money", get: (v) => g(v, "revenue") },
    { key: "cost_of_revenue", label: "Cost of Goods Sold", kind: "money", get: (v) => g(v, "cost_of_revenue") },
    { key: "gross_profit", label: "Gross Profit", kind: "money", get: (v) => g(v, "gross_profit") },
    { key: "rnd", label: "Research & Development", kind: "money", get: (v) => g(v, "rnd") },
    { key: "sga", label: "Selling, General & Admin", kind: "money", get: (v) => g(v, "sga") },
    { key: "dna", label: "Depreciation & Amortization", kind: "money", get: (v) => g(v, "dna") },
    { key: "operating_income", label: "Operating Income", kind: "money", get: (v) => g(v, "operating_income") },
    { key: "ebitda", label: "EBITDA", kind: "money", get: (v) => g(v, "ebitda") },
    { key: "interest_expense", label: "Interest Expense", kind: "money", get: (v) => { const x = g(v, "interest_expense"); return x === null ? null : -Math.abs(x); } },
    { key: "pretax_income", label: "Pre-Tax Income", kind: "money", get: (v) => g(v, "pretax_income") },
    { key: "tax_expense", label: "Tax Provision", kind: "money", get: (v) => g(v, "tax_expense") },
    { key: "net_income", label: "Net Income", kind: "money", get: (v) => g(v, "net_income") },
    { key: "eps_diluted_is", label: "EPS (Diluted)", kind: "pershare", get: (v) => g(v, "eps_diluted") },
    { key: "shares_is", label: "Shares Outstanding (Diluted, M)", kind: "shares", get: (v) => shares(v) },
  ] },
  { id: "balance", title: "Balance Sheet", rows: [
    { key: "cash", label: "Cash and Cash Equivalents", kind: "money", get: (v) => g(v, "cash") },
    { key: "short_term_investments", label: "Short-Term Investments", kind: "money", get: (v) => g(v, "short_term_investments") },
    { key: "receivables", label: "Accounts Receivable", kind: "money", get: (v) => g(v, "receivables") },
    { key: "inventory", label: "Inventories", kind: "money", get: (v) => g(v, "inventory") },
    { key: "current_assets", label: "Total Current Assets", kind: "money", get: (v) => g(v, "current_assets") },
    { key: "ppe_net", label: "Property, Plant & Equipment", kind: "money", get: (v) => g(v, "ppe_net") },
    { key: "goodwill", label: "Goodwill", kind: "money", get: (v) => g(v, "goodwill") },
    { key: "intangibles", label: "Intangible Assets", kind: "money", get: (v) => g(v, "intangibles") },
    { key: "total_assets", label: "Total Assets", kind: "money", get: (v) => g(v, "total_assets") },
    { key: "current_liabilities", label: "Total Current Liabilities", kind: "money", get: (v) => g(v, "current_liabilities") },
    { key: "long_term_debt", label: "Long-Term Debt", kind: "money", get: (v) => g(v, "long_term_debt") },
    { key: "total_debt", label: "Total Debt", kind: "money", get: (v) => g(v, "total_debt") },
    { key: "total_liabilities", label: "Total Liabilities", kind: "money", get: (v) => g(v, "total_liabilities") },
    { key: "retained_earnings", label: "Retained Earnings", kind: "money", get: (v) => g(v, "retained_earnings") },
    { key: "equity", label: "Total Stockholders' Equity", kind: "money", get: (v) => g(v, "equity") },
    { key: "working_capital", label: "Working Capital", kind: "money", get: (v) => g(v, "working_capital") },
    { key: "net_debt", label: "Net Debt", kind: "money", get: (v) => g(v, "net_debt") },
  ] },
  { id: "cashflow", title: "Cashflow Statement", rows: [
    { key: "ocf", label: "Cash Flow from Operations", kind: "money", get: (v) => g(v, "ocf") },
    { key: "capex", label: "Capital Expenditure", kind: "money", get: (v) => { const x = g(v, "capex"); return x === null ? null : -Math.abs(x); } },
    { key: "fcf", label: "Free Cash Flow", kind: "money", get: (v) => g(v, "fcf") },
    { key: "dividends_paid", label: "Cash Flow for Dividends", kind: "money", get: (v) => { const x = g(v, "dividends_paid"); return x === null ? null : -Math.abs(x); } },
    { key: "buybacks", label: "Repurchase of Stock", kind: "money", get: (v) => { const x = g(v, "buybacks"); return x === null ? null : -Math.abs(x); } },
    { key: "dna_cf", label: "Depreciation & Amortization", kind: "money", get: (v) => g(v, "dna") },
  ] },
];

export const MONTHS3 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function colLabel(p: Period): string {
  const m = parseInt(p.end.slice(5, 7), 10);
  return `${MONTHS3[m - 1]} ${p.end.slice(2, 4)}`;
}

/** density 0 = full numbers in $M; 1 = abbreviated (10.5B / 525M); 2 = tighter (3 significant chars) */
export function fmtDense(v: Cell, kind: Kind, density: number): string {
  if (v === null || Number.isNaN(v)) return "-";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  const fix = (x: number, d: number) => x.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
  switch (kind) {
    case "pct": return sign + (a * 100).toFixed(density >= 2 ? 0 : 1) + (density >= 2 ? "%" : "");
    case "ratio": return sign + (a >= 100 ? a.toFixed(0) : a.toFixed(density >= 2 ? 1 : 2));
    case "pershare": return sign + (a >= 1000 ? fix(a, 0) : a.toFixed(2));
    case "price": return sign + (a >= 1000 ? fix(a, 0) : a.toFixed(2));
    case "shares":
    case "money": {
      const m = a / 1e6;
      if (density === 0) return sign + (m >= 1000 ? fix(m, 0) : m >= 10 ? fix(m, 1) : fix(m, 2));
      if (a >= 1e12) return sign + (a / 1e12).toFixed(density >= 2 ? 1 : 2) + "T";
      if (a >= 1e9) return sign + (a / 1e9).toFixed(a >= 1e11 ? 0 : 1) + "B";
      if (a >= 1e6) return sign + (a / 1e6).toFixed(a >= 1e8 ? 0 : 1) + "M";
      return sign + (a / 1e6).toFixed(2) + "M";
    }
  }
}

export function fmtYoy(cur: Cell, prev: Cell): string {
  if (cur === null || prev === null || prev === 0) return "-";
  if ((cur > 0) !== (prev > 0)) return "n/m";
  const c = cur / prev - 1;
  return (c > 0 ? "+" : "") + (c * 100).toFixed(1) + "%";
}

export function toCsv(cols: { label: string }[], sections: typeof SECTIONS, cellsFor: (row: RowDef) => Cell[]): string {
  const lines = [["Metric", ...cols.map((c) => c.label)].join(",")];
  for (const s of sections) {
    lines.push(`"${s.title}"`);
    for (const r of s.rows) lines.push([`"${r.label}"`, ...cellsFor(r).map((v) => (v === null ? "" : String(v)))].join(","));
  }
  return lines.join("\n");
}
