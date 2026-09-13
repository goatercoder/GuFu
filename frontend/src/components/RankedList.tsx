import { Link } from "react-router-dom";
import type { HomePick } from "../api/types";

export default function RankedList({ title, rows, col, fmt, subtitle }: { title: string; subtitle?: string; rows: HomePick[]; col: keyof HomePick; fmt: (v: number | null) => string }) {
  return (
    <div className="card">
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="font-semibold">{title}</h3>
        {subtitle && <span className="text-xs muted">{subtitle}</span>}
      </div>
      {rows.length === 0 ? <div className="text-sm muted">No data yet.</div> : (
        <table className="data">
          <tbody>
            {rows.map((r) => (
              <tr key={r.ticker}>
                <td><Link to={`/company/${r.ticker}`} className="font-semibold hover:underline">{r.ticker}</Link></td>
                <td className="text-2 truncate max-w-[160px]">{r.name}</td>
                <td className="num">{fmt(r[col] as number | null)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
