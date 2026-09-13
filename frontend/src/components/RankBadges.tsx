import { useState } from "react";
import type { CompanyBundle, Rank } from "../api/types";
import { useMetricDefs } from "../api/client";
import { fmtMetric } from "../lib/format";

const LABELS: Record<string, string> = { financial_strength: "Financial Strength", profitability: "Profitability Rank", growth: "Growth Rank", valuation: "Valuation Rank" };
const HINTS: Record<string, string> = {
  financial_strength: "Balance-sheet safety: Altman Z, interest coverage, debt/equity, cash/debt, equity/assets, current ratio, ranked against the S&P 500.",
  profitability: "ROE, ROIC, gross/operating/net margins and Piotroski F-score, ranked against the S&P 500.",
  growth: "5- and 10-year revenue, EPS and free-cash-flow growth plus TTM revenue growth, ranked against the S&P 500.",
  valuation: "Cheapness: P/E, EV/EBITDA, P/B, P/S, FCF yield and PEG, ranked against the S&P 500 (10 = cheapest).",
};

export default function RankBadges({ ranks }: { ranks: CompanyBundle["ranks"] }) {
  const [open, setOpen] = useState<string | null>(null);
  const defs = useMetricDefs();
  const byKey = Object.fromEntries((defs.data ?? []).map((d) => [d.key, d]));
  if (!ranks) return null;
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="rank-badges">
      {(Object.keys(LABELS) as (keyof typeof ranks)[]).map((k) => {
        const r: Rank | undefined = ranks[k];
        const rank = r?.rank ?? null;
        const tone = rank === null ? "na" : rank >= 7 ? "good" : rank <= 3 ? "bad" : "neutral";
        return (
          <div key={k} className="card py-2 relative">
            <button className="w-full text-left" onClick={() => setOpen(open === k ? null : k)} aria-expanded={open === k} title={HINTS[k]}>
              <div className="text-xs uppercase tracking-wide muted">{LABELS[k]}</div>
              <div className="flex items-center gap-2 mt-1">
                <span className={`pill pill-${tone} text-lg`}>{rank === null ? "N/A" : `${rank}/10`}</span>
                <div className="flex gap-0.5 flex-1" aria-hidden="true">
                  {Array.from({ length: 10 }, (_, i) => <span key={i} className="h-2 flex-1 rounded-sm" style={{ background: rank !== null && i < rank ? (tone === "good" ? "var(--good)" : tone === "bad" ? "var(--bad)" : "var(--brand)") : "var(--neutral-bg)" }} />)}
                </div>
              </div>
            </button>
            {open === k && r && (
              <div className="absolute z-20 left-0 right-0 mt-1 card p-2 text-xs shadow-lg">
                <div className="text-2 mb-1">{HINTS[k]}</div>
                <table className="data"><tbody>
                  {r.detail.map((d) => <tr key={d.metric}><td>{byKey[d.metric]?.label ?? d.metric}</td><td className="num">{fmtMetric(byKey[d.metric]?.fmt ?? "ratio", d.value, byKey[d.metric]?.decimals ?? 2)}</td><td className="num muted">{d.percentile}th pct</td></tr>)}
                  {r.detail.length === 0 && <tr><td className="muted">No data for this group.</td></tr>}
                </tbody></table>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
