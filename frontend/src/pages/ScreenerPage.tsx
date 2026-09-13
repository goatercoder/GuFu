import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useFacets, useMetricDefs, useScreener } from "../api/client";
import ScreenerFilters from "../components/ScreenerFilters";
import ScreenerTable from "../components/ScreenerTable";
import ColumnPicker from "../components/ColumnPicker";

const DEFAULT_COLS = ["market_cap", "pe", "peg", "pb", "ps", "ev_ebitda", "dividend_yield", "roe", "roic", "revenue_growth_5y", "piotroski_f", "altman_z"];
const LS_KEY = "gufu.screener.columns";

function loadCols(): string[] {
  try { const v = localStorage.getItem(LS_KEY); if (v) return JSON.parse(v) as string[]; } catch { /* ignore */ }
  return DEFAULT_COLS;
}

export default function ScreenerPage() {
  const [params, setParams] = useSearchParams();
  const [cols, setCols] = useState<string[]>(loadCols);
  const [draft, setDraft] = useState<URLSearchParams>(() => new URLSearchParams(params));
  const facets = useFacets();
  const defsQ = useMetricDefs();
  const defs = useMemo(() => Object.fromEntries((defsQ.data ?? []).map((d) => [d.key, d])), [defsQ.data]);

  // debounce text/number inputs into the URL
  useEffect(() => {
    const h = setTimeout(() => { if (draft.toString() !== params.toString()) setParams(draft, { replace: true }); }, 350);
    return () => clearTimeout(h);
  }, [draft, params, setParams]);
  useEffect(() => { try { localStorage.setItem(LS_KEY, JSON.stringify(cols)); } catch { /* ignore */ } }, [cols]);

  const sort = params.get("sort") ?? "market_cap";
  const order = params.get("order") ?? "desc";
  const page = parseInt(params.get("page") ?? "1", 10) || 1;
  const qs = useMemo(() => { const p = new URLSearchParams(params); p.set("columns", cols.join(",")); p.set("page_size", "50"); if (!p.get("sort")) p.set("sort", sort); if (!p.get("order")) p.set("order", order); return p.toString(); }, [params, cols, sort, order]);
  const { data, isLoading, error } = useScreener(qs);

  const update = (k: string, v: string) => { const p = new URLSearchParams(draft); if (v) p.set(k, v); else p.delete(k); p.delete("page"); setDraft(p); };
  const onSort = (k: string) => { const p = new URLSearchParams(params); const asc = sort === k && order === "desc"; p.set("sort", k); p.set("order", asc ? "asc" : "desc"); p.delete("page"); setDraft(p); setParams(p); };
  const setPage = (n: number) => { const p = new URLSearchParams(params); p.set("page", String(n)); setDraft(p); setParams(p); };
  const reset = () => { const p = new URLSearchParams(); setDraft(p); setParams(p); };
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="grid lg:grid-cols-[290px_1fr] gap-4 items-start">
      <ScreenerFilters facets={facets.data} params={draft} onChange={update} onReset={reset} />
      <div className="card">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
          <div>
            <h2 className="font-semibold text-lg inline">Screener</h2>
            <span className="ml-2 text-sm text-2" data-testid="screener-total">{data ? `${data.total} of ${data.universe} companies match` : isLoading ? "Loading…" : ""}</span>
          </div>
          <div className="flex items-center gap-2">
            <ColumnPicker defs={(defsQ.data ?? []).filter((d) => d.screenable)} selected={cols} onChange={setCols} />
            <button className="btn" onClick={() => setCols(DEFAULT_COLS)}>Default columns</button>
          </div>
        </div>
        <div className="text-xs muted mb-2">Percent filters (yield, ROE, growth, margins) take whole numbers, e.g. 15 for 15%. Market cap in billions is applied as dollars ×1e9. Click a column header to sort; unavailable values sort last.</div>
        {error && <div className="down text-sm">{(error as Error).message}</div>}
        {data && <ScreenerTable data={{ ...data, rows: data.rows }} defs={defs} sort={sort} order={order} onSort={onSort} />}
        {data && (
          <div className="flex items-center justify-between mt-3 text-sm">
            <span className="muted">Page {data.page} of {pages}{data.as_of ? ` · metrics as of ${new Date(data.as_of).toLocaleString()}` : ""}</span>
            <div className="flex gap-1">
              <button className="btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Prev</button>
              <button className="btn" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next →</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
