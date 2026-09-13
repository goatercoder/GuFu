import type { CompanyBundle } from "../api/types";
import { MONTHS, changeClass, fmtDate, fmtMoney, fmtPct, fmtPrice } from "../lib/format";

export default function CompanyHeader({ data }: { data: CompanyBundle }) {
  const { profile, quote, metrics, data_status } = data;
  const lo = quote.low52, hi = quote.high52, p = quote.price;
  const pos = lo !== null && hi !== null && p !== null && hi > lo ? Math.min(100, Math.max(0, ((p - lo) / (hi - lo)) * 100)) : null;
  return (
    <div className="card">
      <div className="flex flex-wrap items-start gap-x-8 gap-y-3">
        <div className="min-w-[260px]">
          <div className="flex items-baseline gap-3">
            <h1 className="text-2xl font-bold">{profile.name}</h1>
            <span className="text-lg font-semibold text-2">{profile.ticker}</span>
          </div>
          <div className="text-sm text-2 mt-1 flex gap-2 flex-wrap">
            <span className="px-2 py-0.5 rounded" style={{ background: "var(--neutral-bg)" }}>{profile.sector}</span>
            <span className="px-2 py-0.5 rounded" style={{ background: "var(--neutral-bg)" }}>{profile.sub_industry}</span>
            {profile.cik && <a className="px-2 py-0.5 rounded hover:underline" style={{ background: "var(--neutral-bg)" }} href={`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${profile.cik}&type=10-&dateb=&owner=include&count=40`} target="_blank" rel="noreferrer">SEC filings ↗</a>}
          </div>
        </div>
        <div>
          <div className="flex items-baseline gap-3">
            <span className="text-3xl font-bold tnum" data-testid="price">{fmtPrice(quote.price)}</span>
            <span className={`text-lg font-semibold tnum ${changeClass(quote.change_pct)}`}>
              {quote.change !== null && (quote.change >= 0 ? "+" : "")}{quote.change?.toFixed(2) ?? ""} ({fmtPct(quote.change_pct, 2, true)})
            </span>
          </div>
          <div className="text-xs muted mt-0.5">
            {quote.stale ? "Last close (live quote unavailable)" : "Live quote"} · {quote.as_of ? fmtDate(quote.as_of) : ""} · {quote.currency}
          </div>
        </div>
        <div className="min-w-[220px] flex-1">
          <div className="flex justify-between text-xs text-2"><span>52w low {fmtPrice(lo)}</span><span>52w high {fmtPrice(hi)}</span></div>
          <div className="relative h-2 mt-1 rounded-full" style={{ background: "var(--neutral-bg)" }}>
            {pos !== null && <div className="absolute -top-1 w-4 h-4 rounded-full border-2" style={{ left: `calc(${pos}% - 8px)`, background: "var(--brand)", borderColor: "var(--surface)" }} title={`${pos.toFixed(0)}% of the 52-week range`} />}
          </div>
          <div className="grid grid-cols-3 gap-2 mt-3 text-sm">
            <div><div className="text-xs muted">Market cap</div><div className="font-semibold tnum">{fmtMoney(metrics.market_cap)}</div></div>
            <div><div className="text-xs muted">Enterprise value</div><div className="font-semibold tnum">{fmtMoney(metrics.enterprise_value)}</div></div>
            <div><div className="text-xs muted">P/E (TTM)</div><div className="font-semibold tnum">{metrics.pe === null ? "N/A" : metrics.pe.toFixed(1)}</div></div>
          </div>
        </div>
      </div>
      <div className="mt-3 pt-3 text-xs muted flex flex-wrap gap-x-5 gap-y-1" style={{ borderTop: "1px solid var(--grid)" }}>
        <span>Fiscal year ends {MONTHS[data_status.fye_month - 1]}</span>
        <span>Latest 10-K filed {fmtDate(data_status.latest_10k_filed)}</span>
        <span>Latest 10-Q filed {fmtDate(data_status.latest_10q_filed)}</span>
        <span>{data_status.annual_years} fiscal years · {data_status.quarters} quarters of XBRL data{data_status.first_fiscal_year ? ` (FY${data_status.first_fiscal_year}–FY${data_status.last_fiscal_year})` : ""}</span>
        <span>TTM basis: {data.inputs.ttm_basis === "annual" ? "latest 10-K" : "last 4 quarters"} ending {fmtDate(data.inputs.ttm_end)}</span>
        {data_status.warnings.length > 0 && <span title={data_status.warnings.join("\n")} style={{ color: "var(--brand-2)" }}>⚠ {data_status.warnings.length} data note{data_status.warnings.length > 1 ? "s" : ""}</span>}
      </div>
    </div>
  );
}
