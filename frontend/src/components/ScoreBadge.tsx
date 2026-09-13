import { useEffect, useRef, useState } from "react";
import type { Scores } from "../api/types";

export function FScoreBadge({ f }: { f: Scores["piotroski_f"] }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onKey); };
  }, [open]);
  if (!f) return <Badge title="Piotroski F-Score" value="N/A" tone="na" />;
  const tone = f.score >= 7 ? "good" : f.score <= 3 ? "bad" : "neutral";
  return (
    <div className="relative" ref={box}>
      <button className="text-left w-full" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <Badge title="Piotroski F-Score" value={`${f.score} / 9`} tone={tone} sub={`FY${f.fiscal_year}${f.prior_fiscal_year ? ` vs FY${f.prior_fiscal_year}` : ""} · click for tests`} />
      </button>
      {open && (
        <ul className="absolute z-10 mt-1 card p-2 text-sm w-80 shadow-lg">
          {f.tests.map((t) => (
            <li key={t.name} className="flex gap-2 py-0.5" title={t.detail}>
              <span className={t.passed ? "up" : t.available ? "down" : "muted"}>{t.passed ? "✓" : t.available ? "✗" : "–"}</span>
              <span>{t.name}{!t.available && <span className="muted"> (n/a)</span>}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ZScoreBadge({ z, sector }: { z: Scores["altman_z"]; sector: string }) {
  if (!z) return <Badge title="Altman Z-Score" value="N/A" tone="na" sub={sector === "Financials" ? "Not meaningful for financials" : "Missing balance-sheet inputs"} />;
  const tone = z.zone === "safe" ? "good" : z.zone === "distress" ? "bad" : "neutral";
  const label = z.zone === "safe" ? "Safe zone" : z.zone === "grey" ? "Grey zone" : "Distress zone";
  return <Badge title="Altman Z-Score" value={z.value.toFixed(2)} tone={tone} sub={z.not_meaningful ? `${label} · not meaningful for financials` : label} />;
}

function Badge({ title, value, tone, sub }: { title: string; value: string; tone: "good" | "bad" | "neutral" | "na"; sub?: string }) {
  return (
    <div className="card py-3 h-full">
      <div className="text-xs uppercase tracking-wide muted">{title}</div>
      <div className="mt-1"><span className={`pill pill-${tone} text-xl`}>{value}</span></div>
      {sub && <div className="text-xs text-2 mt-1">{sub}</div>}
    </div>
  );
}
