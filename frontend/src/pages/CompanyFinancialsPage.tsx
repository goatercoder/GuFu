import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useFinancials, useLegacyRefresh } from "../api/client";
import FinancialChart from "../components/FinancialChart";
import FinancialsTable, { periodsToCsv } from "../components/FinancialsTable";
import { fmtDate } from "../lib/format";
import type { CompanyContext } from "./CompanyShell";

export default function CompanyFinancialsPage() {
  const { ticker: t, data: company } = useOutletContext<CompanyContext>();
  const [freq, setFreq] = useState<"annual" | "quarterly">("annual");
  const [showFilings, setShowFilings] = useState(false);
  const fin = useFinancials(t, freq);
  const refresh = useLegacyRefresh(t);
  const d = fin.data;
  const cov = d?.coverage;
  const legacyCount = d?.periods.filter((p) => p.legacy).length ?? 0;

  const download = () => {
    if (!d) return;
    const csv = periodsToCsv(d.periods, freq);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${t}_${freq}_financials.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <div className="space-y-4" data-testid="financials-page">
      <FinancialChart ticker={t} />
      <div className="card">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
          <div>
            <h2 className="font-semibold text-lg inline">{freq === "annual" ? "30-year financials" : "Quarterly financials"}</h2>
            <span className="ml-2 text-xs muted">{company.profile.name} · values in $ millions except per-share</span>
          </div>
          <div className="flex gap-2 flex-wrap items-center">
            <div className="flex gap-1">
              <button className={`btn ${freq === "annual" ? "btn-active" : ""}`} onClick={() => setFreq("annual")}>Annual</button>
              <button className={`btn ${freq === "quarterly" ? "btn-active" : ""}`} onClick={() => setFreq("quarterly")}>Quarterly</button>
            </div>
            <button className="btn" onClick={download} disabled={!d} data-testid="csv-button">Download CSV</button>
            {freq === "annual" && (
              <button className="btn" onClick={() => refresh.mutate()} disabled={refresh.isPending || d?.legacy_status === "building"} title="Re-fetch and re-parse the older 10-K filings">
                {refresh.isPending ? "Re-extracting…" : "Re-extract older years"}
              </button>
            )}
          </div>
        </div>
        {d?.legacy_status === "building" && (
          <div className="text-sm mb-2 px-3 py-2 rounded" style={{ background: "var(--neutral-bg)" }}>
            Fetching the company's older 10-K filings from SEC EDGAR to fill in years before {cov?.xbrl_from ?? 2009}… this table updates automatically.
          </div>
        )}
        {fin.isLoading ? <div className="skeleton h-96" /> : fin.error ? <div className="down text-sm">{(fin.error as Error).message}</div> : d && (
          <FinancialsTable periods={d.periods} freq={freq} windowFrom={cov?.window_from} windowTo={cov?.window_to ?? undefined} />
        )}
        {d && (
          <div className="text-xs muted mt-3 space-y-1">
            {freq === "annual" && cov && (
              <div data-testid="coverage">
                Coverage: {cov.xbrl_from ? `XBRL filings FY${cov.xbrl_from}–FY${cov.xbrl_to}` : "no XBRL data"}
                {legacyCount > 0 && cov.legacy_from && ` · older 10-K filings FY${cov.legacy_from}–FY${cov.legacy_to} (${legacyCount} years)`}
                {" · "}{cov.years_available} of 30 years available{cov.missing_years.length > 0 && `, missing ${cov.missing_years.join(", ")}`}
              </div>
            )}
            <div>{d.coverage_note}</div>
            {freq === "annual" && d.legacy_filings.length > 0 && (
              <div>
                <button className="underline" onClick={() => setShowFilings((s) => !s)}>{showFilings ? "Hide" : "Show"} the {d.legacy_filings.length} older filings used</button>
                {showFilings && (
                  <ul className="mt-1 space-y-0.5">
                    {d.legacy_filings.map((f) => (
                      <li key={f.accn}>
                        <a className="underline" href={f.url} target="_blank" rel="noreferrer">{f.form} for FY{f.fiscal_year ?? "?"}</a> filed {fmtDate(f.filed)} · years {f.years.length ? `${Math.min(...f.years)}–${Math.max(...f.years)}` : "none"} · sections: {Object.entries(f.sections).filter(([, v]) => v).map(([k]) => k).join(", ") || "none found"}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            {d.legacy_warnings.length > 0 && (
              <details>
                <summary className="cursor-pointer" style={{ color: "var(--brand-2)" }}>{d.legacy_warnings.length} note{d.legacy_warnings.length > 1 ? "s" : ""} from parsing older filings</summary>
                <ul className="mt-1 list-disc ml-4">{d.legacy_warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
              </details>
            )}
            {refresh.data && <div>Re-extraction {refresh.data.status}: {refresh.data.legacy_years.length} legacy years.</div>}
          </div>
        )}
      </div>
    </div>
  );
}
