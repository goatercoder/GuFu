import { useState } from "react";
import type { MetricDef } from "../api/types";

export default function ColumnPicker({ defs, selected, onChange }: { defs: MetricDef[]; selected: string[]; onChange: (cols: string[]) => void }) {
  const [open, setOpen] = useState(false);
  const groups = new Map<string, MetricDef[]>();
  for (const d of defs) { if (!groups.has(d.group)) groups.set(d.group, []); groups.get(d.group)!.push(d); }
  const toggle = (k: string) => onChange(selected.includes(k) ? selected.filter((c) => c !== k) : [...selected, k]);
  return (
    <div className="relative">
      <button className="btn" onClick={() => setOpen((o) => !o)} aria-expanded={open}>Columns ({selected.length})</button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 card p-3 w-[520px] max-h-[420px] overflow-auto shadow-lg text-sm">
          <div className="grid grid-cols-2 gap-x-4">
            {[...groups.entries()].map(([g, ds]) => (
              <div key={g} className="mb-2">
                <div className="text-xs uppercase muted mb-1">{g}</div>
                {ds.map((d) => (
                  <label key={d.key} className="flex items-center gap-2 py-0.5 cursor-pointer">
                    <input type="checkbox" checked={selected.includes(d.key)} onChange={() => toggle(d.key)} />
                    <span title={d.explanation}>{d.label}</span>
                  </label>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
