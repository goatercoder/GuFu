import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import HomePage from "./pages/HomePage";
import CompanyPage from "./pages/CompanyPage";
import CompanyShell from "./pages/CompanyShell";
import CompanyFinancialsPage from "./pages/CompanyFinancialsPage";
import ScreenerPage from "./pages/ScreenerPage";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/company/:ticker" element={<CompanyShell />}>
          <Route index element={<CompanyPage />} />
          <Route path="financials" element={<CompanyFinancialsPage />} />
        </Route>
        <Route path="/screener" element={<ScreenerPage />} />
        <Route path="*" element={<div className="card">Page not found.</div>} />
      </Routes>
    </Layout>
  );
}
