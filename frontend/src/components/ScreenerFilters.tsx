import type { Facets } from "../api/types";

export const RANGE_FILTERS: { key: string; label: string; unit?: string }[] = [
  { key: "market_cap", label: "Market cap ($B)" },
  { key: "pe", label: "P/E" },
  { key: "peg", label: "PEG" },
  { key: "pb", label: "P/B" },
  { key: "ps", label: "P/S" },
  { key: "ev_ebitda", label: "EV/EBITDA" },
  { key: "dividend_yield", label: "Dividend yield (%)" },
  { key: "roe", label: "ROE (%)" },
  { key: "roic", label: "ROIC (%)" },
  { key: "net_margin", label: "Net margin (%)" },
  { key: "revenue_growth_5y", label: "Revenue growth 5y (%)" },
  { key: "eps_growth_5y", label: "EPS growth 5y (%)" },
  { key: "debt_to_equity", label: "Debt/Equity" },
  { key: "piotroski_f", label: "F-Score" },
  { key: "altman_z", label: "Z-Score" },
  { key: "margin_of_safety", label: "Margin of safety (%)" },
];

export default function ScreenerFilters({ facets, params, onChange, onReset }: { facets?: Facets; params: URLSearchParams; onChange: (k: string, v: string) => void; onReset: () => void }) {
  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold">Filters</h3>
        <button className="btn" onClick={onReset}>Reset</button>
      </div>
      <label className="block text-sm mb-2">
        <span className="text-2 text-xs">Sector</span>
        <select className="input" value={params.get("sector") ?? ""} onChange={(e) => onChange("sector", e.target.value)}>
          <option value="">All sectors</option>
          {facets?.sectors.map((s) => <option key={s.name} value={s.name}>{s.name} ({s.count})</option>)}
        </select>
      </label>
      <label className="block text-sm mb-3">
        <span className="text-2 text-xs">Name or ticker contains</span>
        <input className="input" value={params.get("q") ?? ""} onChange={(e) => onChange("q", e.target.value)} placeholder="e.g. bank" />
      </label>
      <div className="grid grid-cols-1 gap-2">
        {RANGE_FILTERS.map((f) => (
          <div key={f.key} className="grid grid-cols-[1fr_70px_70px] gap-1 items-center text-xs">
            <span className="text-2">{f.label}</span>
            <input className="input" placeholder="min" inputMode="decimal" value={params.get(`${f.key}_min`) ?? ""} onChange={(e) => onChange(`${f.key}_min`, e.target.value)} aria-label={`${f.label} minimum`} />
            <input className="input" placeholder="max" inputMode="decimal" value={params.get(`${f.key}_max`) ?? ""} onChange={(e) => onChange(`${f.key}_max`, e.target.value)} aria-label={`${f.label} maximum`} />
          </div>
        ))}
      </div>
    </div>
  );
}
