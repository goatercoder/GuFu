import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useMe } from "./api/hooks";
import { SystemProvider, useSystem } from "./system";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import Login from "./pages/Login";
import Setup from "./pages/Setup";
import Dashboard from "./pages/Dashboard";
import Controls from "./pages/Controls";
import ControlDetail from "./pages/ControlDetail";
import Poam, { PoamNew } from "./pages/Poam";
import PoamDetail from "./pages/PoamDetail";
import EvidencePage from "./pages/EvidencePage";
import Assets from "./pages/Assets";
import { ProviderDetail, ProvidersList } from "./pages/Providers";
import Agents from "./pages/Agents";
import Reports from "./pages/Reports";
import Settings from "./pages/Settings";

function Shell() {
  const { ready, systemCount } = useSystem();

  if (!ready) return <Spinner />;
  if (systemCount === 0) return <Navigate to="/setup" replace />;

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/controls" element={<Controls />} />
        <Route path="/controls/:controlId" element={<ControlDetail />} />
        <Route path="/poam" element={<Poam />} />
        <Route path="/poam/new" element={<PoamNew />} />
        <Route path="/poam/:itemId" element={<PoamDetail />} />
        <Route path="/evidence" element={<EvidencePage />} />
        <Route path="/assets" element={<Assets />} />
        <Route path="/providers" element={<ProvidersList />} />
        <Route path="/providers/:providerId" element={<ProviderDetail />} />
        <Route path="/agents" element={<Agents />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}

export default function App() {
  const me = useMe();
  const location = useLocation();

  if (me.isLoading) return <Spinner />;

  const authenticated = me.data?.authenticated ?? false;
  if (!authenticated) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  if (location.pathname === "/login") return <Navigate to="/" replace />;

  return (
    <SystemProvider>
      <Routes>
        <Route path="/setup" element={<Setup />} />
        <Route path="*" element={<Shell />} />
      </Routes>
    </SystemProvider>
  );
}
