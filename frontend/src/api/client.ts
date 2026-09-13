/**
 * Data access layer. Two modes:
 *  - server mode (default): talks to the FastAPI backend under /api
 *  - static mode (VITE_STATIC_DATA=1): reads the JSON files produced by scripts/export_static.py, so the
 *    whole app can be hosted as static files (GitHub Pages). Screener filtering runs in the browser.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { CompanyBundle, CompanyListItem, Facets, FinancialsResponse, Health, HomeResponse, MetricDef, PricesResponse, ScreenerResponse, ScreenerRow, SetupResponse } from "./types";

export const STATIC = import.meta.env.VITE_STATIC_DATA === "1";
const BASE = (import.meta.env.BASE_URL || "/").replace(/\/?$/, "/");
const dataUrl = (p: string) => `${BASE}data/${p}`;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* ignore */ }
    if (STATIC && r.status === 404) detail = "This company is not in the published dataset yet.";
    throw new ApiError(r.status, detail);
  }
  return (await r.json()) as T;
}

// ---------------------------------------------------------------- static-mode helpers
interface StaticFinancials extends Omit<FinancialsResponse, "freq" | "periods"> { annual: FinancialsResponse["periods"]; quarterly: FinancialsResponse["periods"] }
interface StaticPrices { ticker: string; symbol: string; currency: string; meta: Record<string, number | string>; first_date: string | null; source: string; ranges: Record<string, { downsampled: boolean; points: PricesResponse["points"] }> }
interface StaticScreener { as_of: string | null; universe: number; rows: ScreenerRow[]; fixture_mode: boolean }

let screenerCache: Promise<StaticScreener> | null = null;
let defsCache: Promise<MetricDef[]> | null = null;
const loadScreener = () => (screenerCache ??= get<StaticScreener>(dataUrl("screener.json")));
const loadDefs = () => (defsCache ??= get<MetricDef[]>(dataUrl("definitions.json")));

const BASE_COLUMNS = ["ticker", "name", "sector", "sub_industry"];
const DEFAULT_COLS = ["market_cap", "pe", "peg", "pb", "ps", "ev_ebitda", "dividend_yield", "roe", "roic", "revenue_growth_5y", "piotroski_f", "altman_z"];

async function staticScreener(qs: string): Promise<ScreenerResponse> {
  const [data, defs] = await Promise.all([loadScreener(), loadDefs()]);
  const byKey = Object.fromEntries(defs.map((d) => [d.key, d]));
  const p = new URLSearchParams(qs);
  let rows = data.rows;
  const sector = p.get("sector"), sub = p.get("sub_industry"), q = p.get("q")?.toLowerCase();
  if (sector) rows = rows.filter((r) => r.sector === sector);
  if (sub) rows = rows.filter((r) => r.sub_industry === sub);
  if (q) rows = rows.filter((r) => r.ticker.toLowerCase().includes(q) || (r.name ?? "").toLowerCase().includes(q));
  for (const [k, v] of p.entries()) {
    if (!(k.endsWith("_min") || k.endsWith("_max"))) continue;
    const key = k.slice(0, -4), kind = k.slice(-3);
    const def = byKey[key];
    if (!def?.screenable) continue;
    let val = parseFloat(v);
    if (Number.isNaN(val)) continue;
    if (def.fmt === "pct") val /= 100;
    rows = rows.filter((r) => { const x = r[key]; return typeof x === "number" && (kind === "min" ? x >= val : x <= val); });
  }
  const sort = p.get("sort") ?? "market_cap", order = p.get("order") ?? "desc";
  const isBase = BASE_COLUMNS.includes(sort);
  const present = rows.filter((r) => (isBase ? true : typeof r[sort] === "number"));
  const absent = isBase ? [] : rows.filter((r) => typeof r[sort] !== "number");
  present.sort((a, b) => {
    const x = a[sort], y = b[sort];
    const c = isBase ? String(x ?? "").localeCompare(String(y ?? "")) : (x as number) - (y as number);
    return order === "asc" ? c : -c;
  });
  const all = [...present, ...absent];
  const page = Math.max(1, parseInt(p.get("page") ?? "1", 10) || 1);
  const size = Math.max(1, Math.min(500, parseInt(p.get("page_size") ?? "50", 10) || 50));
  const cols = (p.get("columns")?.split(",").filter((c) => c && byKey[c]) ?? []);
  const columns = cols.length ? cols : DEFAULT_COLS;
  const keep = [...BASE_COLUMNS, "price", "change_pct", "price_as_of", ...columns];
  const pageRows = all.slice((page - 1) * size, page * size).map((r) => Object.fromEntries(keep.map((k) => [k, r[k] ?? null])) as ScreenerRow);
  return { total: all.length, page, page_size: size, rows: pageRows, columns, as_of: data.as_of, universe: data.universe, fixture_mode: data.fixture_mode };
}

async function staticHealth(): Promise<Health> {
  const meta = await get<{ built_at: string; companies: number; fixture_mode: boolean }>(dataUrl("meta.json"));
  return { status: "ok", fixture_mode: meta.fixture_mode, setup_required: false, companies: meta.companies, metrics_cached: meta.companies, building: false, current_job_id: null, static: true, built_at: meta.built_at };
}

// ---------------------------------------------------------------- public API
export const fetchCompanies = () => get<CompanyListItem[]>(STATIC ? dataUrl("companies.json") : "/api/companies");
export const fetchCompany = (t: string) => get<CompanyBundle>(STATIC ? dataUrl(`company/${encodeURIComponent(t)}.json`) : `/api/company/${encodeURIComponent(t)}`);
export async function fetchFinancials(t: string, freq: "annual" | "quarterly"): Promise<FinancialsResponse> {
  if (!STATIC) return get<FinancialsResponse>(`/api/company/${encodeURIComponent(t)}/financials?freq=${freq}`);
  const d = await get<StaticFinancials>(dataUrl(`financials/${encodeURIComponent(t)}.json`));
  const { annual, quarterly, ...rest } = d;
  return { ...rest, freq, periods: freq === "annual" ? annual : quarterly };
}
export async function fetchPrices(t: string, range: string): Promise<PricesResponse> {
  if (!STATIC) return get<PricesResponse>(`/api/company/${encodeURIComponent(t)}/prices?range=${range}`);
  const d = await get<StaticPrices>(dataUrl(`prices/${encodeURIComponent(t)}.json`));
  const r = d.ranges[range] ?? d.ranges["1y"];
  return { ticker: d.ticker, symbol: d.symbol, currency: d.currency, range, downsampled: r.downsampled, points: r.points, meta: d.meta, first_date: d.first_date, source: d.source };
}
export const fetchScreener = (qs: string) => (STATIC ? staticScreener(qs) : get<ScreenerResponse>(`/api/screener?${qs}`));
export const fetchFacets = () => get<Facets>(STATIC ? dataUrl("facets.json") : "/api/screener/facets");
export const fetchDefs = () => (STATIC ? loadDefs() : get<MetricDef[]>("/api/metrics/definitions"));
export const fetchHome = () => get<HomeResponse>(STATIC ? dataUrl("home.json") : "/api/home");
export const fetchHealth = () => (STATIC ? staticHealth() : get<Health>("/api/health"));

export const useCompanies = () => useQuery({ queryKey: ["companies"], queryFn: fetchCompanies, staleTime: 10 * 60_000 });
export const useCompany = (ticker: string) => useQuery({ queryKey: ["company", ticker], queryFn: () => fetchCompany(ticker), retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 2 });
export const useFinancials = (ticker: string, freq: "annual" | "quarterly") => useQuery({
  queryKey: ["financials", ticker, freq],
  queryFn: () => fetchFinancials(ticker, freq),
  refetchInterval: (q) => (!STATIC && q.state.data?.legacy_status === "building" ? 4000 : false),
});
export const usePrices = (ticker: string, range: string) => useQuery({ queryKey: ["prices", ticker, range], queryFn: () => fetchPrices(ticker, range) });
export const useScreener = (qs: string) => useQuery({ queryKey: ["screener", qs], queryFn: () => fetchScreener(qs), placeholderData: (prev) => prev });
export const useFacets = () => useQuery({ queryKey: ["facets"], queryFn: fetchFacets });
export const useMetricDefs = () => useQuery({ queryKey: ["metricdefs"], queryFn: fetchDefs, staleTime: Infinity });
export const useHome = () => useQuery({ queryKey: ["home"], queryFn: fetchHome, refetchInterval: (q) => (!STATIC && q.state.data?.job?.status === "running" ? 5000 : false) });
export const useHealth = () => useQuery({ queryKey: ["health"], queryFn: fetchHealth, refetchInterval: STATIC ? false : 15_000 });

export async function postSetup(name: string, email: string): Promise<SetupResponse> {
  if (STATIC) throw new ApiError(400, "Not needed on the hosted site");
  const r = await fetch("/api/admin/setup", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify({ name, email }) });
  if (!r.ok) {
    let detail = r.statusText;
    try { const j = await r.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* ignore */ }
    throw new ApiError(r.status, detail);
  }
  return (await r.json()) as SetupResponse;
}

export function useSetup() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: ({ name, email }: { name: string; email: string }) => postSetup(name, email), onSuccess: () => qc.invalidateQueries() });
}

export async function postLegacyRefresh(ticker: string): Promise<{ status: string; legacy_years: number[]; warnings: string[] }> {
  if (STATIC) throw new ApiError(400, "Re-extraction runs in the nightly data build on the hosted site");
  const r = await fetch(`/api/company/${encodeURIComponent(ticker)}/legacy/refresh`, { method: "POST", headers: { Accept: "application/json" } });
  if (!r.ok) throw new ApiError(r.status, r.statusText);
  return (await r.json()) as { status: string; legacy_years: number[]; warnings: string[] };
}

export function useLegacyRefresh(ticker: string) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: () => postLegacyRefresh(ticker), onSuccess: () => { qc.invalidateQueries({ queryKey: ["financials", ticker] }); qc.invalidateQueries({ queryKey: ["company", ticker] }); } });
}
