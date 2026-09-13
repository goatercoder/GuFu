import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCompanies } from "../api/client";
import type { CompanyListItem } from "../api/types";

function rank(items: CompanyListItem[], q: string): CompanyListItem[] {
  const s = q.trim().toLowerCase();
  if (!s) return [];
  const scored: [number, CompanyListItem][] = [];
  for (const c of items) {
    const t = c.ticker.toLowerCase();
    const n = c.name.toLowerCase();
    let score = -1;
    if (t === s) score = 0;
    else if (t.startsWith(s)) score = 1;
    else if (n.startsWith(s)) score = 2;
    else if (n.split(/[\s(]+/).some((w) => w.startsWith(s))) score = 3;
    else if (n.includes(s) || t.includes(s)) score = 4;
    if (score >= 0) scored.push([score, c]);
  }
  scored.sort((a, b) => a[0] - b[0] || a[1].ticker.localeCompare(b[1].ticker));
  return scored.slice(0, 10).map((x) => x[1]);
}

export default function SearchBar({ compact = false, autoFocus = false }: { compact?: boolean; autoFocus?: boolean }) {
  const { data } = useCompanies();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const nav = useNavigate();
  const box = useRef<HTMLDivElement>(null);
  const results = useMemo(() => rank(data ?? [], q), [data, q]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const go = (c: CompanyListItem) => { setOpen(false); setQ(""); nav(`/company/${c.ticker}`); };

  return (
    <div ref={box} className="relative" data-testid="search">
      <input
        className={`input ${compact ? "" : "text-base py-2.5 px-4"}`}
        placeholder="Search S&P 500 by ticker or company name…"
        value={q}
        autoFocus={autoFocus}
        aria-label="Search companies"
        onChange={(e) => { setQ(e.target.value); setOpen(true); setIdx(0); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(i + 1, results.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
          else if (e.key === "Enter" && results[idx]) go(results[idx]);
          else if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && results.length > 0 && (
        <ul className="absolute z-20 mt-1 w-full card p-1 shadow-lg max-h-96 overflow-auto" role="listbox">
          {results.map((c, i) => (
            <li key={c.ticker} role="option" aria-selected={i === idx}
                className="px-3 py-1.5 rounded cursor-pointer flex justify-between gap-3 text-sm"
                style={i === idx ? { background: "var(--neutral-bg)" } : {}}
                onMouseEnter={() => setIdx(i)} onMouseDown={() => go(c)}>
              <span><span className="font-semibold">{c.ticker}</span> <span className="text-2">{c.name}</span></span>
              <span className="muted text-xs whitespace-nowrap">{c.sector}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
