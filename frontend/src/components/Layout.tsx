import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import SearchBar from "./SearchBar";
import { STATIC, useHealth } from "../api/client";
import SetupCard from "./SetupCard";

export default function Layout({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const health = useHealth();
  const navCls = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-1.5 rounded-md text-sm font-medium text-white ${isActive ? "gf-nav-active" : "opacity-85 hover:opacity-100"}`;
  return (
    <div className="min-h-screen">
      <header className="gf-header">
        <div className="max-w-[1500px] mx-auto px-4 py-2 flex items-center gap-4 flex-wrap">
          <Link to="/" className="flex items-center gap-2 font-bold text-xl tracking-tight text-white">
            <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="6" fill="#fff" /><path d="M6 22l6-8 5 5 9-11" stroke="var(--brand)" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
            GuFu
          </Link>
          <nav className="flex items-center gap-1">
            <NavLink to="/" end className={navCls}>Home</NavLink>
            <NavLink to="/screener" className={navCls}>Screener</NavLink>
          </nav>
          {pathname !== "/" && (
            <div className="flex-1 min-w-[240px] max-w-xl ml-auto"><SearchBar compact /></div>
          )}
          {health.data?.fixture_mode && (
            <span className="text-xs px-2 py-1 rounded" style={{ background: "var(--bad-bg)", color: "var(--bad)" }} title="GUFU_FIXTURE_MODE=1: bundled sample data, not live market data">
              SAMPLE DATA MODE
            </span>
          )}
          {health.data?.static && health.data.built_at && (
            <span className="text-xs text-white opacity-85" title="This is the free hosted edition: all data is rebuilt every night from SEC filings and closing prices.">
              Data as of {new Date(health.data.built_at).toLocaleDateString()}
            </span>
          )}
        </div>
      </header>
      <main className="max-w-[1500px] mx-auto px-4 py-4">{!STATIC && health.data?.setup_required ? <SetupCard /> : children}</main>
      <footer className="max-w-[1500px] mx-auto px-4 py-6 text-xs muted">
        Financial statements: SEC EDGAR XBRL (10-K / 10-Q filings). Prices: Yahoo Finance. Metrics computed by GuFu. Not investment advice.
        <span className="block mt-1">© 2026 goatercoder. All rights reserved. Personal, non-commercial use only.</span>
      </footer>
    </div>
  );
}
