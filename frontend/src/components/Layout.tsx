import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import SearchBar from "./SearchBar";
import { useHealth } from "../api/client";

export default function Layout({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const health = useHealth();
  const navCls = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-1.5 rounded-md text-sm font-medium ${isActive ? "text-white" : "text-2 hover:opacity-80"}`;
  return (
    <div className="min-h-screen">
      <header style={{ background: "var(--surface)", borderBottom: "1px solid var(--border)" }}>
        <div className="max-w-7xl mx-auto px-4 py-2.5 flex items-center gap-4 flex-wrap">
          <Link to="/" className="flex items-center gap-2 font-bold text-lg tracking-tight">
            <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="6" fill="var(--brand)" /><path d="M6 22l6-8 5 5 9-11" stroke="#fff" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
            GuFu
          </Link>
          <nav className="flex items-center gap-1">
            <NavLink to="/" end className={navCls} style={({ isActive }) => (isActive ? { background: "var(--brand)" } : {})}>Overview</NavLink>
            <NavLink to="/screener" className={navCls} style={({ isActive }) => (isActive ? { background: "var(--brand)" } : {})}>Screener</NavLink>
          </nav>
          {pathname !== "/" && (
            <div className="flex-1 min-w-[240px] max-w-xl ml-auto"><SearchBar compact /></div>
          )}
          {health.data?.fixture_mode && (
            <span className="text-xs px-2 py-1 rounded" style={{ background: "var(--bad-bg)", color: "var(--bad)" }} title="GUFU_FIXTURE_MODE=1: bundled sample data, not live market data">
              SAMPLE DATA MODE
            </span>
          )}
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-4 py-5">{children}</main>
      <footer className="max-w-7xl mx-auto px-4 py-6 text-xs muted">
        Financial statements: SEC EDGAR XBRL (10-K / 10-Q filings). Prices: Yahoo Finance. Metrics computed by GuFu. Not investment advice.
      </footer>
    </div>
  );
}
