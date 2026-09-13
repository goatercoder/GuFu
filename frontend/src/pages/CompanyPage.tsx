import { useOutletContext } from "react-router-dom";
import MetricTable from "../components/MetricTable";
import PriceChart from "../components/PriceChart";
import FinancialChart from "../components/FinancialChart";
import DcfPanel from "../components/DcfPanel";
import { FScoreBadge, ZScoreBadge } from "../components/ScoreBadge";
import RankBadges from "../components/RankBadges";
import type { CompanyContext } from "./CompanyShell";

export default function CompanyPage() {
  const { data, ticker: t } = useOutletContext<CompanyContext>();
  const groups = Object.fromEntries(data.groups.map((g) => [g.group, g]));
  return (
    <div className="space-y-4">
      <RankBadges ranks={data.ranks} />
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
