import { useQuery } from "@tanstack/react-query";
import type { CompanyBundle, CompanyListItem, Facets, FinancialsResponse, Health, HomeResponse, MetricDef, PricesResponse, ScreenerResponse } from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* ignore */ }
    throw new ApiError(r.status, detail);
  }
  return (await r.json()) as T;
}

export const useCompanies = () => useQuery({ queryKey: ["companies"], queryFn: () => get<CompanyListItem[]>("/api/companies"), staleTime: 10 * 60_000 });
export const useCompany = (ticker: string) => useQuery({ queryKey: ["company", ticker], queryFn: () => get<CompanyBundle>(`/api/company/${encodeURIComponent(ticker)}`), retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 2 });
export const useFinancials = (ticker: string, freq: "annual" | "quarterly") => useQuery({ queryKey: ["financials", ticker, freq], queryFn: () => get<FinancialsResponse>(`/api/company/${encodeURIComponent(ticker)}/financials?freq=${freq}`) });
export const usePrices = (ticker: string, range: string) => useQuery({ queryKey: ["prices", ticker, range], queryFn: () => get<PricesResponse>(`/api/company/${encodeURIComponent(ticker)}/prices?range=${range}`) });
export const useScreener = (qs: string) => useQuery({ queryKey: ["screener", qs], queryFn: () => get<ScreenerResponse>(`/api/screener?${qs}`), placeholderData: (prev) => prev });
export const useFacets = () => useQuery({ queryKey: ["facets"], queryFn: () => get<Facets>("/api/screener/facets") });
export const useMetricDefs = () => useQuery({ queryKey: ["metricdefs"], queryFn: () => get<MetricDef[]>("/api/metrics/definitions"), staleTime: Infinity });
export const useHome = () => useQuery({ queryKey: ["home"], queryFn: () => get<HomeResponse>("/api/home"), refetchInterval: (q) => (q.state.data?.job?.status === "running" ? 5000 : 60_000) });
export const useHealth = () => useQuery({ queryKey: ["health"], queryFn: () => get<Health>("/api/health"), refetchInterval: 15_000 });
