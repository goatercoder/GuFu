import { Link, useOutletContext } from "react-router-dom";
import { changeClass, fmtMoney, fmtPct, fmtPrice, fmtRatio } from "../lib/format";
import type { CompanyContext } from "./CompanyShell";

export default function PeersPage() {
  const { data } = useOutletContext<CompanyContext>();
  const me = { ticker: data.profile.ticker, name: data.profile.name, sub_industry: data.profile.sub_industry, price: data.quote.price, change_pct: data.quote.change_pct, market_cap: data.metrics.market_cap, pe: data.metrics.pe, peg: data.metrics.peg, pb: data.metrics.pb, ev_ebitda: data.metrics.ev_ebitda, dividend_yield: data.metrics.dividend_yield, roe: data.metrics.roe, roic: data.metrics.roic, net_margin: data.metrics.net_margin, revenue_growth_5y: data.metrics.revenue_growth_5y, piotroski_f: data.metrics.piotroski_f };
  const rows = [me, ...data.peers];
  return (
    <div className="card" data-testid="peers-page">
      <h3 className="font-semibold mb-1">Peers</h3>
      <div className="text-xs muted mb-2">{data.profile.sub_industry} · largest S&P 500 companies in the same industry, {data.profile.ticker} first</div>
      <div className="overflow-x-auto">
        <table className="data">
          <thead><tr><th>Ticker</th><th>Company</th><th className="num">Price</th><th className="num">Chg</th><th className="num">Market cap</th><th className="num">P/E</th><th className="num">PEG</th><th className="num">P/B</th><th className="num">EV/EBITDA</th><th className="num">Yield</th><th className="num">ROE</th><th className="num">ROIC</th><th className="num">Net margin</th><th className="num">Rev growth 5y</th><th className="num">F-score</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.ticker} style={i === 0 ? { background: "var(--surface-2)", fontWeight: 600 } : undefined}>
                <td><Link className="hover:underline" to={`/company/${r.ticker}`}>{r.ticker}</Link></td><td className="max-w-[200px] truncate">{r.name}</td>
                <td className="num">{fmtPrice(r.price)}</td><td className={`num ${changeClass(r.change_pct)}`}>{fmtPct(r.change_pct, 2, true)}</td>
                <td className="num">{fmtMoney(r.market_cap, 1)}</td><td className="num">{fmtRatio(r.pe, 1)}</td><td className="num">{fmtRatio(r.peg, 2)}</td><td className="num">{fmtRatio(r.pb, 2)}</td><td className="num">{fmtRatio(r.ev_ebitda, 1)}</td>
                <td className="num">{fmtPct(r.dividend_yield, 2)}</td><td className="num">{fmtPct(r.roe, 1)}</td><td className="num">{fmtPct(r.roic, 1)}</td><td className="num">{fmtPct(r.net_margin, 1)}</td><td className="num">{fmtPct(r.revenue_growth_5y, 1)}</td><td className="num">{r.piotroski_f ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
