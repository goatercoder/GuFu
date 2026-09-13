import { useState } from "react";
import type { DcfBlock } from "../api/types";
import { dcfTwoStage, marginOfSafety } from "../lib/dcf";
import { fmtPct, fmtPrice } from "../lib/format";

export default function DcfPanel({ dcf, price, graham }: { dcf: DcfBlock; price: number | null; graham: number | null }) {
  const a = dcf.assumptions;
  const [g1, setG1] = useState(Math.round(dcf.eps.growth * 1000) / 10);
  const [g2, setG2] = useState(a.terminal_growth * 100);
  const [r, setR] = useState(a.discount_rate * 100);
  const [basis, setBasis] = useState<"eps" | "fcf">("eps");
  const base = basis === "eps" ? a.base_eps : a.base_fcf_per_share;
  const value = dcfTwoStage(base, g1 / 100, g2 / 100, r / 100, a.stage1_years, a.stage2_years);
  const mos = marginOfSafety(value, price);
  const tone = mos === null ? "na" : mos > 0.2 ? "good" : mos < -0.2 ? "bad" : "neutral";

  return (
    <div className="card" data-testid="dcf">
      <div className="flex items-baseline justify-between flex-wrap gap-2">
        <h3 className="font-semibold">Intrinsic value (DCF)</h3>
        <div className="flex gap-1">
          <button className={`btn ${basis === "eps" ? "btn-active" : ""}`} onClick={() => setBasis("eps")}>Earnings</button>
          <button className={`btn ${basis === "fcf" ? "btn-active" : ""}`} onClick={() => setBasis("fcf")}>Free cash flow</button>
        </div>
      </div>
      <div className="grid sm:grid-cols-3 gap-3 mt-3 items-end">
        <div>
          <div className="text-xs muted">Fair value / share</div>
          <div className="text-2xl font-semibold tnum">{fmtPrice(value)}</div>
          <div className="text-xs text-2">vs price {fmtPrice(price)}</div>
        </div>
        <div>
          <div className="text-xs muted">Margin of safety</div>
          <div><span className={`pill pill-${tone} text-lg`}>{fmtPct(mos, 1, true)}</span></div>
        </div>
        <div>
          <div className="text-xs muted">Graham number</div>
          <div className="text-lg font-semibold tnum">{fmtPrice(graham)}</div>
        </div>
      </div>
      <div className="grid sm:grid-cols-3 gap-3 mt-4 text-sm">
        <Slider label={`Growth, years 1–${a.stage1_years}`} value={g1} min={0} max={30} step={0.5} onChange={setG1} />
        <Slider label={`Terminal growth, years ${a.stage1_years + 1}–${a.stage1_years + a.stage2_years}`} value={g2} min={0} max={8} step={0.5} onChange={setG2} />
        <Slider label="Discount rate" value={r} min={5} max={20} step={0.5} onChange={setR} />
      </div>
      <p className="text-xs muted mt-3">
        Base: {basis === "eps" ? `TTM diluted EPS ${fmtPrice(a.base_eps)}` : `TTM free cash flow per share ${fmtPrice(a.base_fcf_per_share)}`}.
        Default growth is the 5-year historical {basis === "eps" ? "EPS" : "FCF"} CAGR clamped to 0–{Math.round(a.growth_cap * 100)}%; terminal {Math.round(a.terminal_growth * 100)}%, discount {Math.round(a.discount_rate * 100)}%. A model, not a forecast.
      </p>
    </div>
  );
}

function Slider({ label, value, min, max, step, onChange }: { label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void }) {
  return (
    <label className="block">
      <div className="flex justify-between"><span className="text-2">{label}</span><span className="font-semibold tnum">{value.toFixed(1)}%</span></div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(parseFloat(e.target.value))} className="w-full accent-[var(--brand)]" />
    </label>
  );
}
