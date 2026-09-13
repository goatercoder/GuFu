export interface CompanyListItem { ticker: string; name: string; sector: string; sub_industry: string; has_data: boolean }

export interface Quote {
  price: number | null; prev_close: number | null; change: number | null; change_pct: number | null;
  high52: number | null; low52: number | null; as_of: string | null; currency: string; stale: boolean;
}

export interface MetricItem { key: string; label: string; fmt: string; value: number | null; color: "good" | "bad" | "neutral" | "na"; explanation: string; decimals: number }
export interface MetricGroup { group: string; label: string; items: MetricItem[] }

export interface FTest { name: string; passed: boolean; available: boolean; detail: string }
export interface Scores {
  altman_z: { value: number; zone: "safe" | "grey" | "distress"; not_meaningful?: boolean; components: Record<string, number> } | null;
  piotroski_f: { score: number; tests: FTest[]; fiscal_year: number; prior_fiscal_year: number | null } | null;
}

export interface DcfBlock {
  eps: { value: number | null; margin_of_safety: number | null; growth: number };
  fcf: { value: number | null; margin_of_safety: number | null; growth: number };
  assumptions: { base_eps: number | null; base_fcf_per_share: number | null; discount_rate: number; terminal_growth: number; stage1_years: number; stage2_years: number; growth_cap: number };
}

export interface RankDetail { metric: string; value: number; percentile: number }
export interface Rank { rank: number | null; percentile: number | null; detail: RankDetail[] }
export interface Peer { ticker: string; name: string; sub_industry: string; price: number | null; change_pct: number | null; market_cap: number | null; pe: number | null; peg: number | null; pb: number | null; ev_ebitda: number | null; dividend_yield: number | null; roe: number | null; roic: number | null; net_margin: number | null; revenue_growth_5y: number | null; piotroski_f: number | null }
export interface CompanyBundle {
  profile: { ticker: string; name: string; sector: string; sub_industry: string; cik: number | null };
  quote: Quote;
  metrics: Record<string, number | null>;
  ranks: Record<"financial_strength" | "profitability" | "growth" | "valuation", Rank>;
  peers: Peer[];
  groups: MetricGroup[];
  scores: Scores;
  dcf: DcfBlock;
  inputs: { shares: number | null; ttm_end: string | null; ttm_basis: string; balance_end: string | null; tax_rate: number };
  data_status: {
    latest_10k_filed: string | null; latest_10q_filed: string | null; fye_month: number; annual_years: number; quarters: number;
    first_fiscal_year: number | null; last_fiscal_year: number | null; warnings: string[]; entity_name: string; fixture_mode: boolean; built_at?: string;
  };
}

export interface PeriodSource { accn: string; form: string; filed: string; url: string; filing_fy: number | null; methods: string[]; fields: Record<string, string> }
export interface Period { key: string; end: string; start: string | null; fy: number; fq: number | null; label: string; form: string; filed: string | null; v: Record<string, number>; src: Record<string, string>; derived: string[]; legacy?: boolean; source?: PeriodSource | null; px?: number | null }
export interface Coverage { window_from: number; window_to: number | null; xbrl_from: number | null; xbrl_to: number | null; legacy_from: number | null; legacy_to: number | null; years_available: number; missing_years: number[] }
export interface LegacyFiling { accn: string; form: string; filed: string; fiscal_year: number | null; url: string; years: number[]; documents: string[]; sections: Record<string, boolean> }
export interface FinancialsResponse {
  ticker: string; freq: "annual" | "quarterly"; fye_month: number; fields: { key: string; label: string; kind: string; unit: string }[];
  periods: Period[]; ttm: Period | null; warnings: string[]; source: string; coverage_note: string;
  legacy_status: "ready" | "building" | "none" | "disabled" | string; coverage: Coverage; legacy_warnings: string[]; legacy_filings: LegacyFiling[];
}

export interface PricePoint { d: string; c: number; v: number }
export interface PricesResponse { ticker: string; symbol: string; currency: string; range: string; downsampled: boolean; points: PricePoint[]; meta: Record<string, number | string>; first_date: string | null; source: string }

export interface ScreenerRow { ticker: string; name: string; sector: string; sub_industry: string; price: number | null; change_pct: number | null; [k: string]: number | string | null }
export interface ScreenerResponse { total: number; page: number; page_size: number; rows: ScreenerRow[]; columns: string[]; as_of: string | null; universe: number; fixture_mode: boolean }
export interface MetricDef { key: string; label: string; group: string; fmt: string; explanation: string; good: [number | null, number | null] | null; bad: [number | null, number | null] | null; screenable: boolean; decimals: number }
export interface Facets { sectors: { name: string; count: number }[]; sub_industries: { name: string; count: number }[]; screenable: MetricDef[]; default_columns: string[] }

export interface HomePick { ticker: string; name: string; sector: string; price: number | null; change_pct: number | null; market_cap: number | null; pe: number | null; roe: number | null; dividend_yield: number | null; peg: number | null; margin_of_safety: number | null; piotroski_f: number | null }
export interface HomeResponse {
  as_of: string | null; fixture_mode: boolean;
  stats: { companies: number; with_data: number; with_price: number; total_market_cap: number | null; median_pe: number | null; median_dividend_yield: number | null; advancers: number; decliners: number };
  sectors: { sector: string; count: number; market_cap: number; median_pe: number | null; avg_change_pct: number | null }[];
  movers: { gainers: HomePick[]; losers: HomePick[] };
  cheapest_pe: HomePick[]; highest_roe: HomePick[]; undervalued_dcf: HomePick[]; quality: HomePick[]; largest: HomePick[];
  job: { id: number; kind: string; status: string; total: number; done: number; failed: number } | null;
}
export interface Health { status: string; fixture_mode: boolean; setup_required: boolean; companies: number; metrics_cached: number; building: boolean; current_job_id: number | null; static?: boolean; built_at?: string }
export interface SetupResponse { status: string; user_agent: string; persisted: "env" | "db"; setup_required: boolean }
