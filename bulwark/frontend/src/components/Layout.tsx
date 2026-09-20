import { NavLink, useNavigate } from "react-router-dom";
import { useReadiness, useLogout, useOrganization, useScore, useSystems } from "../api/hooks";
import { useSystem } from "../system";
import type { ReactNode } from "react";

const icons: Record<string, ReactNode> = {
  dashboard: <path d="M3 3h7v7H3zM14 3h7v4h-7zM14 10h7v11h-7zM3 13h7v8H3z" />,
  controls: <path d="M4 5h16M4 12h16M4 19h16" />,
  poam: <path d="M9 5h10M9 12h10M9 19h10M4 5l1 1 2-2M4 12l1 1 2-2M4 19l1 1 2-2" />,
  evidence: <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM13 2v7h7" />,
  assets: <path d="M4 5h16v10H4zM8 20h8M12 15v5" />,
  providers: <path d="M18 10a4 4 0 0 0-7.7-1.5A3.5 3.5 0 0 0 6 12a3.5 3.5 0 0 0 .5 7h11a3.5 3.5 0 0 0 .5-9z" />,
  agents: <path d="M12 3v3M5.6 5.6l2.1 2.1M3 12h3M18 12h3M16.4 7.7l2.1-2.1M9 20h6M12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6z" />,
  reports: <path d="M5 21V8M12 21V3M19 21v-9" />,
  settings: <path d="M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 7.4 19.4l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3 15H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.1-2.7l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 9 3.6V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1.3z" />,
};

function Icon({ name }: { name: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {icons[name]}
    </svg>
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  const { systemId, setSystemId } = useSystem();
  const { data: systems } = useSystems();
  const { data: organization } = useOrganization();
  const { data: score } = useScore(systemId);
  const { data: readiness } = useReadiness(systemId);
  const logout = useLogout();
  const navigate = useNavigate();

  const openPoam = readiness?.open_poam_count ?? 0;
  const findings = readiness?.findings_count ?? 0;
  const scoreTone = !score ? "neutral"
    : score.sprs_score >= 88 ? "good"
      : score.sprs_score >= 0 ? "warning" : "critical";

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2l8 4v6c0 5-3.4 8.7-8 10-4.6-1.3-8-5-8-10V6z" />
            </svg>
          </span>
          <span>
            <div className="brand-name">Bulwark</div>
            <div className="brand-sub">CMMC Level 2</div>
          </span>
        </div>

        <nav className="nav">
          <NavLink to="/" end className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
            <Icon name="dashboard" />Dashboard
          </NavLink>
          <NavLink to="/controls" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
            <Icon name="controls" />Requirements
            {score ? <span className="nav-count">{score.met_count}/{score.total}</span> : null}
          </NavLink>
          <NavLink to="/poam" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
            <Icon name="poam" />Plan of action
            {openPoam ? <span className="nav-count">{openPoam}</span> : null}
          </NavLink>
          <NavLink to="/evidence" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
            <Icon name="evidence" />Evidence
          </NavLink>
          <NavLink to="/assets" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
            <Icon name="assets" />Assets &amp; scope
          </NavLink>
          <NavLink to="/providers" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
            <Icon name="providers" />Providers
          </NavLink>
          <NavLink to="/agents" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
            <Icon name="agents" />Agents
            {findings ? <span className="nav-count alert">{findings}</span> : null}
          </NavLink>
          <NavLink to="/reports" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
            <Icon name="reports" />Documents
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
            <Icon name="settings" />Settings
          </NavLink>
        </nav>
      </aside>

      <div className="main">
        <header className="topbar">
          <span className="topbar-org">{organization?.name ?? "Bulwark"}</span>
          {systems && systems.length > 1 ? (
            <select
              className="compact"
              value={systemId ?? ""}
              onChange={(event) => setSystemId(Number(event.target.value))}
              aria-label="Select system"
            >
              {systems.map((system) => (
                <option key={system.id} value={system.id}>{system.name}</option>
              ))}
            </select>
          ) : systems && systems.length === 1 ? (
            <span style={{ color: "var(--ink-secondary)" }}>{systems[0].name}</span>
          ) : null}

          <div className="topbar-spacer" />

          {score ? (
            <span className={`badge ${scoreTone}`} title="SPRS score out of 110">
              SPRS {score.sprs_score}
            </span>
          ) : null}
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => logout.mutate(undefined, { onSuccess: () => navigate("/login") })}
          >
            Sign out
          </button>
        </header>

        <main className="content">{children}</main>
      </div>
    </div>
  );
}
