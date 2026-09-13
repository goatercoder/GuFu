import { useOutletContext } from "react-router-dom";
import ThirtyYear from "../components/ThirtyYear";
import FinancialChart from "../components/FinancialChart";
import type { CompanyContext } from "./CompanyShell";

export default function CompanyFinancialsPage() {
  const { ticker: t, data } = useOutletContext<CompanyContext>();
  return (
    <div className="space-y-4" data-testid="financials-page">
      <ThirtyYear ticker={t} name={data.profile.name} />
      <FinancialChart ticker={t} />
    </div>
  );
}
