import type { MetricGroup } from "../api/types";
import { fmtMetric } from "../lib/format";

export default function MetricTable({ group }: { group: MetricGroup }) {
  return (
    <div className="card" data-testid="metric-table">
      <h3 className="font-semibold mb-2">{group.label}</h3>
      <table className="data">
        <tbody>
          {group.items.map((it) => (
            <tr key={it.key}>
              <td>
                <span className="inline-flex items-center gap-1">
                  {it.label}
                  <span className="muted cursor-help text-xs" title={it.explanation} aria-label={it.explanation}>ⓘ</span>
                </span>
              </td>
              <td className="num">
                <span className={`pill pill-${it.color}`}>{fmtMetric(it.fmt, it.value, it.decimals)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
