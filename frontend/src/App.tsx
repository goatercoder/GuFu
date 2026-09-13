import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import HomePage from "./pages/HomePage";
import CompanyPage from "./pages/CompanyPage";
import CompanyShell from "./pages/CompanyShell";
import CompanyFinancialsPage from "./pages/CompanyFinancialsPage";
import ValuationPage from "./pages/ValuationPage";
import DividendPage from "./pages/DividendPage";
import PeersPage from "./pages/PeersPage";
import ScreenerPage from "./pages/ScreenerPage";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/company/:ticker" element={<CompanyShell />}>
          <Route index element={<CompanyPage />} />
          <Route path="financials" element={<CompanyFinancialsPage />} />
          <Route path="valuation" element={<ValuationPage />} />
          <Route path="dividend" element={<DividendPage />} />
          <Route path="peers" element={<PeersPage />} />
        </Route>
        <Route path="/screener" element={<ScreenerPage />} />
        <Route path="*" element={<div className="card">Page not found.</div>} />
      </Routes>
    </Layout>
  );
}
