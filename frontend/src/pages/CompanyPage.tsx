import { useParams } from "react-router-dom";
import { ApiError, useCompany } from "../api/client";
import CompanyHeader from "../components/CompanyHeader";
import MetricTable from "../components/MetricTable";
import PriceChart from "../components/PriceChart";
import FinancialChart from "../components/FinancialChart";
import DcfPanel from "../components/DcfPanel";
import { FScoreBadge, ZScoreBadge } from "../components/ScoreBadge";

export default function CompanyPage() {
  const { ticker = "" } = useParams();
  const t = ticker.toUpperCase();
  const { data, isLoading, error, refetch } = useCompany(t);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="skeleton h-32" />
        <div className="text-sm muted">Loading {t}… the first visit fetches the company's full SEC XBRL history and price series, which can take several seconds.</div>
        <div className="skeleton h-72" />
      </div>
    );
  }
  if (error) {
    const e = error as ApiError;
    return (
      <div className="card">
        <h2 className="font-semibold text-lg mb-1">{e.status === 404 ? `${t} is not in the S&P 500 universe` : `Could not load ${t}`}</h2>
        <p className="text-sm text-2">{e.message}</p>
        {e.status !== 404 && <button className="btn mt-3" onClick={() => refetch()}>Retry</button>}
      </div>
    );
  }
  if (!data) return null;
  const groups = Object.fromEntries(data.groups.map((g) => [g.group, g]));
  return (
    <div className="space-y-4">
      <CompanyHeader data={data} />
      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2"><PriceChart ticker={t} fairValue={data.dcf.eps.value} /></div>
        <div className="grid grid-rows-2 gap-4">
          <FScoreBadge f={data.scores.piotroski_f} />
          <ZScoreBadge z={data.scores.altman_z} sector={data.profile.sector} />
        </div>
      </div>
      <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
        {groups.valuation && <MetricTable group={groups.valuation} />}
        {groups.profitability && <MetricTable group={groups.profitability} />}
        {groups.strength && <MetricTable group={groups.strength} />}
        {groups.growth && <MetricTable group={groups.growth} />}
        {groups.dividend && <MetricTable group={groups.dividend} />}
        {groups.pershare && <MetricTable group={groups.pershare} />}
      </div>
      <FinancialChart ticker={t} />
      <DcfPanel dcf={data.dcf} price={data.quote.price} graham={data.metrics.graham_number} />
    </div>
  );
}
