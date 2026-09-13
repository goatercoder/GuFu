import { Link } from "react-router-dom";
import { useHome } from "../api/client";
import SearchBar from "../components/SearchBar";
import StatTile from "../components/StatTile";
import SectorBreakdown from "../components/SectorBreakdown";
import RankedList from "../components/RankedList";
import { fmtInt, fmtMoney, fmtPct, fmtRatio } from "../lib/format";

export default function HomePage() {
  const { data, isLoading, error } = useHome();
  const s = data?.stats;
  const job = data?.job;
  const building = job?.status === "running";
  return (
    <div className="space-y-5">
      <section className="card py-8 text-center">
        <h1 className="text-3xl font-bold mb-1">S&amp;P 500 stock research</h1>
        <p className="text-2 mb-5">Valuation, quality and growth metrics computed from SEC filings and live prices.</p>
        <div className="max-w-2xl mx-auto"><SearchBar autoFocus /></div>
        <div className="text-xs muted mt-3">Try <Link className="underline" to="/company/AAPL">AAPL</Link>, <Link className="underline" to="/company/MSFT">MSFT</Link>, <Link className="underline" to="/company/BRK.B">BRK.B</Link> or open the <Link className="underline" to="/screener">screener</Link>.</div>
      </section>

      {building && (
        <div className="card text-sm" style={{ borderColor: "var(--brand)" }}>
          <div className="flex justify-between"><span>Building the data cache ({job.kind}): {job.done} / {job.total} steps{job.failed ? `, ${job.failed} failed` : ""}</span><span className="muted">refreshes automatically</span></div>
          <div className="h-1.5 mt-2 rounded-full" style={{ background: "var(--neutral-bg)" }}><div className="h-full rounded-full" style={{ width: `${Math.min(100, (100 * job.done) / Math.max(1, job.total))}%`, background: "var(--brand)" }} /></div>
        </div>
      )}
      {error && <div className="card text-sm down">Could not load the market overview: {(error as Error).message}</div>}

      <section className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3" data-testid="stat-tiles">
        <StatTile label="Companies" value={isLoading ? "…" : `${s?.with_data ?? 0} / ${s?.companies ?? 0}`} sub="with computed metrics" />
        <StatTile label="Total market cap" value={fmtMoney(s?.total_market_cap ?? null, 1)} />
        <StatTile label="Median P/E" value={fmtRatio(s?.median_pe ?? null, 1)} sub="trailing twelve months" />
        <StatTile label="Median dividend yield" value={fmtPct(s?.median_dividend_yield ?? null, 2)} />
        <StatTile label="Advancers" value={fmtInt(s?.advancers ?? null)} tone="up" sub="vs previous close" />
        <StatTile label="Decliners" value={fmtInt(s?.decliners ?? null)} tone="down" sub="vs previous close" />
      </section>

      <section className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">{data && <SectorBreakdown sectors={data.sectors} />}</div>
        <RankedList title="Largest companies" rows={data?.largest ?? []} col="market_cap" fmt={(v) => fmtMoney(v, 1)} />
      </section>

      <section className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
        <RankedList title="Top gainers" subtitle="1-day" rows={data?.movers.gainers ?? []} col="change_pct" fmt={(v) => fmtPct(v, 2, true)} />
        <RankedList title="Top losers" subtitle="1-day" rows={data?.movers.losers ?? []} col="change_pct" fmt={(v) => fmtPct(v, 2, true)} />
        <RankedList title="Lowest P/E" subtitle="positive earnings" rows={data?.cheapest_pe ?? []} col="pe" fmt={(v) => fmtRatio(v, 1)} />
        <RankedList title="Highest ROE" rows={data?.highest_roe ?? []} col="roe" fmt={(v) => fmtPct(v, 1)} />
        <RankedList title="Largest DCF discount" subtitle="margin of safety" rows={data?.undervalued_dcf ?? []} col="margin_of_safety" fmt={(v) => fmtPct(v, 0, true)} />
        <RankedList title="Highest F-Score" subtitle="Piotroski" rows={data?.quality ?? []} col="piotroski_f" fmt={(v) => fmtInt(v)} />
      </section>
      {data?.as_of && <div className="text-xs muted">Metrics cache built {new Date(data.as_of).toLocaleString()}.{data.fixture_mode ? " Running on bundled sample data (GUFU_FIXTURE_MODE=1), not live market data." : ""}</div>}
    </div>
  );
}
