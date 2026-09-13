import { useEffect, useMemo, useRef, useState } from "react";
import { STATIC, useFinancials, useLegacyRefresh } from "../api/client";
import type { Period } from "../api/types";
import { SECTIONS, colLabel, fmtDense, fmtYoy, toCsv, type Cell, type RowDef } from "../lib/fin";
import { fmtDate } from "../lib/format";
import Sparkline from "./Sparkline";

type Col = { id: string; label: string; period: Period | null; kind: "annual" | "ttm" | "quarter"; legacy: boolean; yoyPrev?: Period | null };
const YEAR_CHOICES = [10, 15, 20, 30];

export default function ThirtyYear({ ticker, name }: { ticker: string; name: string }) {
  const annual = useFinancials(ticker, "annual");
  const quarterly = useFinancials(ticker, "quarterly");
  const refresh = useLegacyRefresh(ticker);
  const [years, setYears] = useState(30);
  const [view, setView] = useState<"$" | "YoY">("$");
  const [showFilings, setShowFilings] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1200);

  useEffect(() => {
    if (!wrap.current) return;
    const ro = new ResizeObserver((e) => setWidth(e[0].contentRect.width));
    ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);

  const cols: Col[] = useMemo(() => {
    const a = annual.data, q = quarterly.data;
    if (!a) return [];
    const byFy = new Map(a.periods.map((p) => [p.fy, p]));
    const to = a.coverage?.xbrl_to ?? (a.periods.length ? a.periods[a.periods.length - 1].fy : new Date().getFullYear());
    const out: Col[] = [];
    for (let fy = to - years + 1; fy <= to; fy++) {
      const p = byFy.get(fy) ?? null;
      out.push({ id: `fy${fy}`, label: p ? colLabel(p) : `'${String(fy).slice(2)}`, period: p, kind: "annual", legacy: !!p?.legacy, yoyPrev: byFy.get(fy - 1) ?? null });
    }
    if (a.ttm) out.push({ id: "ttm", label: "TTM", period: a.ttm, kind: "ttm", legacy: false, yoyPrev: null });
    if (q) {
      const last = q.periods.slice(-5);
      for (const p of last) {
        const prev = q.periods.find((x) => x.fy === p.fy - 1 && x.fq === p.fq) ?? null;
        out.push({ id: p.key, label: colLabel(p), period: p, kind: "quarter", legacy: false, yoyPrev: prev });
      }
    }
    return out;
  }, [annual.data, quarterly.data, years]);

  const nAnnual = cols.filter((c) => c.kind === "annual").length;
  const labelW = width < 900 ? 150 : 190;
  const trendW = width < 900 ? 0 : 56;
  const colW = cols.length ? Math.max(30, Math.floor((width - labelW - trendW - 16) / cols.length)) : 60;
  const density = colW >= 68 ? 0 : colW >= 44 ? 1 : 2;
  const fontPx = colW >= 60 ? 12 : colW >= 44 ? 11 : colW >= 36 ? 10 : 9;

  const cellsFor = (row: RowDef): Cell[] => cols.map((c) => (c.period ? row.get(c.period.v, c.period.px ?? null) : null));
  const yoyFor = (row: RowDef): string[] => cols.map((c) => {
    if (!c.period) return "-";
    const cur = row.get(c.period.v, c.period.px ?? null);
    const prev = c.yoyPrev ? row.get(c.yoyPrev.v, c.yoyPrev.px ?? null) : null;
    return fmtYoy(cur, prev);
  });

  const download = () => {
    const csv = toCsv(cols, SECTIONS, cellsFor);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const el = document.createElement("a");
    el.href = url; el.download = `${ticker}_30y_financials.csv`; el.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const a = annual.data;
  const cov = a?.coverage;
  const legacyCount = a?.periods.filter((p) => p.legacy).length ?? 0;

  return (
    <div ref={wrap} className="space-y-3" data-testid="thirty-year">
      <div className="card py-2 flex items-center gap-3 flex-wrap sticky top-0 z-20" style={{ background: "var(--surface)" }}>
        <nav className="flex gap-3 text-sm font-medium flex-wrap">
          {SECTIONS.map((s) => <a key={s.id} href={`#${s.id}`} className="hover:underline">{s.title}</a>)}
        </nav>
        <div className="ml-auto flex items-center gap-2 flex-wrap text-xs">
          <span className="muted">Years</span>
          <div className="flex gap-1">{YEAR_CHOICES.map((y) => <button key={y} className={`btn ${years === y ? "btn-active" : ""}`} onClick={() => setYears(y)}>{y}</button>)}</div>
          <span className="muted ml-2">View</span>
          <div className="flex gap-1"><button className={`btn ${view === "$" ? "btn-active" : ""}`} onClick={() => setView("$")}>$</button><button className={`btn ${view === "YoY" ? "btn-active" : ""}`} onClick={() => setView("YoY")}>YoY %</button></div>
          <button className="btn" onClick={download} disabled={!a} data-testid="csv-button">CSV</button>
          {!STATIC && <button className="btn" onClick={() => refresh.mutate()} disabled={refresh.isPending || a?.legacy_status === "building"} title="Re-fetch and re-parse the older 10-K filings">{refresh.isPending ? "Re-extracting…" : "Re-extract older years"}</button>}
        </div>
      </div>
      {a?.legacy_status === "building" && (
        <div className="text-sm px-3 py-2 rounded" style={{ background: "var(--neutral-bg)" }}>
          Fetching older 10-K filings from SEC EDGAR for the years before {cov?.xbrl_from ?? 2009}… the tables update automatically.
        </div>
      )}
      {annual.isLoading ? <div className="skeleton h-96" /> : annual.error ? <div className="down text-sm card">{(annual.error as Error).message}</div> : a && (
        SECTIONS.map((sec) => {
          const rows = sec.rows.filter((r) => cellsFor(r).some((v) => v !== null));
          if (!rows.length) return null;
          return (
            <section key={sec.id} id={sec.id} className="card p-0 overflow-hidden" data-testid={`section-${sec.id}`}>
              <div className="flex items-center justify-between px-3 py-2" style={{ borderBottom: "1px solid var(--grid)" }}>
                <h3 className="font-semibold">{sec.title} <span className="text-xs muted font-normal ml-2">{sec.id === "income" || sec.id === "balance" || sec.id === "cashflow" ? "USD, millions" : "USD"}</span></h3>
                <div className="text-xs muted">Annuals ({nAnnual}) · TTM · last 5 quarters</div>
              </div>
              <div className="fy-scroll">
                <table className="fy" style={{ fontSize: fontPx, width: "100%", tableLayout: "fixed" }}>
                  <colgroup>
                    <col style={{ width: labelW }} />
                    {trendW > 0 && <col style={{ width: trendW }} />}
                    {cols.map((c) => <col key={c.id} style={{ width: colW }} />)}
                  </colgroup>
                  <thead>
                    <tr>
                      <th className="lab">Fiscal Period</th>
                      {trendW > 0 && <th className="trend">Trend</th>}
                      {cols.map((c) => (
                        <th key={c.id} className={`num ${c.kind} ${c.legacy ? "legacy" : ""}`} title={headerTitle(c)}>
                          {c.legacy && c.period?.source ? <a href={c.period.source.url} target="_blank" rel="noreferrer">{c.label}</a> : c.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => {
                      const vals = cellsFor(r);
                      const yoy = view === "YoY" ? yoyFor(r) : null;
                      const trendVals = vals.slice(0, nAnnual);
                      return (
                        <tr key={r.key}>
                          <td className="lab" title={r.label}>{r.label}</td>
                          {trendW > 0 && <td className="trend"><Sparkline values={trendVals} /></td>}
                          {cols.map((c, i) => {
                            const v = vals[i];
                            const text = yoy ? yoy[i] : fmtDense(v, r.kind, density);
                            const neg = yoy ? text.startsWith("-") : v !== null && v < 0;
                            return <td key={c.id} className={`num ${c.kind} ${c.legacy ? "legacy" : ""} ${neg ? "neg" : ""}`} title={cellTitle(c, r, v, density)}>{text}</td>;
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          );
        })
      )}
      {a && (
        <div className="text-xs muted space-y-1 px-1">
          {cov && (
            <div data-testid="coverage">
              Coverage: {cov.xbrl_from ? `XBRL filings FY${cov.xbrl_from}–FY${cov.xbrl_to}` : "no XBRL data"}
              {legacyCount > 0 && cov.legacy_from && ` · older 10-K filings FY${cov.legacy_from}–FY${cov.legacy_to} (${legacyCount} years, italic)`}
              {" · "}{cov.years_available} of 30 years available{cov.missing_years.length > 0 && `, missing ${cov.missing_years.join(", ")}`}
            </div>
          )}
          <div>{a.coverage_note} Ratios use the fiscal-period-end stock price. Negative values are shown in red.</div>
          {a.legacy_filings.length > 0 && (
            <div>
              <button className="underline" onClick={() => setShowFilings((s) => !s)}>{showFilings ? "Hide" : "Show"} the {a.legacy_filings.length} older filings used</button>
              {showFilings && (
                <ul className="mt-1 space-y-0.5">
                  {a.legacy_filings.map((f) => (
                    <li key={f.accn}><a className="underline" href={f.url} target="_blank" rel="noreferrer">{f.form} for FY{f.fiscal_year ?? "?"}</a> filed {fmtDate(f.filed)} · years {f.years.length ? `${Math.min(...f.years)}–${Math.max(...f.years)}` : "none"} · {Object.entries(f.sections).filter(([, v]) => v).map(([k]) => k).join(", ") || "no tables found"}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {a.legacy_warnings.length > 0 && (
            <details><summary className="cursor-pointer" style={{ color: "var(--brand-2)" }}>{a.legacy_warnings.length} note{a.legacy_warnings.length > 1 ? "s" : ""} from parsing older filings</summary>
              <ul className="mt-1 list-disc ml-4">{a.legacy_warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></details>
          )}
          {refresh.data && <div>Re-extraction {refresh.data.status}: {refresh.data.legacy_years.length} legacy years.</div>}
          <div>{name} · {ticker}</div>
        </div>
      )}
    </div>
  );
}

function headerTitle(c: Col): string {
  if (!c.period) return "No filing data for this year";
  if (c.kind === "ttm") return `Trailing twelve months ending ${c.period.end}`;
  if (c.legacy && c.period.source) return `Parsed from the ${c.period.source.form} filed ${c.period.source.filed} (click to open the filing)`;
  return `${c.period.label} · ${c.period.form} · period end ${c.period.end}${c.period.filed ? ` · filed ${c.period.filed}` : ""}`;
}

function cellTitle(c: Col, r: RowDef, v: Cell, density: number): string | undefined {
  if (v === null || !c.period) return undefined;
  const full = fmtDense(v, r.kind, 0);
  const base = density > 0 ? `${r.label}: ${full}${r.kind === "money" || r.kind === "shares" ? " M" : ""}` : r.label;
  if (c.legacy && c.period.source) {
    const m = c.period.source.fields?.[r.key];
    const how = m ? (m.startsWith("summary") ? "Selected Financial Data table" : `${m.split(" ")[0]} statement`) : "older 10-K filing";
    return `${base} · from the ${c.period.source.form} (${how}), filed ${c.period.source.filed}`;
  }
  return `${base} · ${c.period.label}`;
}
