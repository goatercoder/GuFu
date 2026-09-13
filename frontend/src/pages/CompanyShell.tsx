import { NavLink, Outlet, useParams } from "react-router-dom";
import { ApiError, useCompany } from "../api/client";
import type { CompanyBundle } from "../api/types";
import CompanyHeader from "../components/CompanyHeader";

export type CompanyContext = { data: CompanyBundle; ticker: string };

export default function CompanyShell() {
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
  const tab = ({ isActive }: { isActive: boolean }) => `px-4 py-2 text-sm font-medium border-b-2 ${isActive ? "border-[var(--brand)] text-[var(--text)]" : "border-transparent text-2 hover:text-[var(--text)]"}`;
  return (
    <div className="space-y-4">
      <CompanyHeader data={data} />
      <nav className="flex gap-1" style={{ borderBottom: "1px solid var(--grid)" }} aria-label="Company sections">
        <NavLink to={`/company/${t}`} end className={tab}>Summary</NavLink>
        <NavLink to={`/company/${t}/financials`} className={tab} data-testid="tab-financials">30-Y Financials</NavLink>
        <NavLink to={`/company/${t}/valuation`} className={tab} data-testid="tab-valuation">Valuation</NavLink>
        <NavLink to={`/company/${t}/dividend`} className={tab} data-testid="tab-dividend">Dividend</NavLink>
        <NavLink to={`/company/${t}/peers`} className={tab} data-testid="tab-peers">Peers</NavLink>
      </nav>
      <Outlet context={{ data, ticker: t } satisfies CompanyContext} />
    </div>
  );
}
