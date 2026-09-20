/** Charts for the readiness dashboard.
 *
 *  Colour follows the validated status palette (green / amber / blue / red, grey for
 *  not-applicable). Amber sits below 3:1 on a light surface by design, so every chart pairs colour
 *  with a text label and offers the same numbers as a table. No dual axes anywhere.
 */
import { useState } from "react";
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { ScoreFamily, ScoreResult, ScoreSnapshot } from "../api/types";
import { STATUS_META, STATUS_ORDER, formatDate } from "./ui";
import type { ImplementationStatus } from "../api/types";

const AXIS = "#7b828d";
const GRID = "#dfe3e8";

/** The headline number: SPRS score on its real -203..110 scale, with the 88-point threshold. */
export function ScoreHero({ score }: { score: ScoreResult }) {
  const { sprs_score: value, max_score: max, min_score: min } = score;
  const span = max - min;
  const position = Math.max(0, Math.min(1, (value - min) / span));
  const threshold = (88 - min) / span;
  const tone = value >= 88 ? "var(--status-good)"
    : value >= 0 ? "var(--status-warning)"
      : "var(--status-critical)";

  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <div style={{ fontSize: 52, fontWeight: 700, letterSpacing: "-0.03em", lineHeight: 1, color: tone }}>
          {value}
        </div>
        <div style={{ color: "var(--ink-secondary)", fontSize: 14 }}>
          of {max} &middot; SPRS score
        </div>
      </div>

      <div style={{ marginTop: 14, position: "relative" }}>
        <div style={{ height: 10, borderRadius: 5, background: "var(--neutral-wash)", overflow: "hidden" }}>
          <div style={{
            width: `${position * 100}%`, height: "100%", background: tone,
            borderTopRightRadius: 4, borderBottomRightRadius: 4,
          }} />
        </div>
        <div
          title="88 points: the minimum for a Conditional CMMC Status"
          style={{
            position: "absolute", top: -4, left: `${threshold * 100}%`,
            width: 2, height: 18, background: "var(--ink)", opacity: 0.55,
          }}
        />
        <div style={{
          display: "flex", justifyContent: "space-between",
          fontSize: 11, color: "var(--ink-muted)", marginTop: 5,
        }}>
          <span className="mono">{min}</span>
          <span style={{ marginLeft: `${Math.max(0, threshold * 100 - 12)}%` }}>88 threshold</span>
          <span className="mono">{max}</span>
        </div>
      </div>
    </div>
  );
}

/** Requirements met per family. One measure, one series: no legend needed, the title names it. */
export function FamilyBars({ families, onSelect }: {
  families: ScoreFamily[];
  onSelect?: (familyId: string) => void;
}) {
  const [hover, setHover] = useState<string | null>(null);
  return (
    <div>
      {families.map((family) => {
        const pct = family.total ? (family.met / family.total) * 100 : 0;
        const complete = family.met === family.total;
        const active = hover === family.id;
        return (
          <button
            key={family.id}
            type="button"
            onMouseEnter={() => setHover(family.id)}
            onMouseLeave={() => setHover(null)}
            onClick={() => onSelect?.(family.id)}
            title={`${family.abbr} ${family.name}: ${family.met} of ${family.total} met, ${family.deducted_points} points deducted`}
            style={{
              display: "grid", gridTemplateColumns: "minmax(0, 1.1fr) minmax(70px, 1fr) auto",
              gap: 10, alignItems: "center",
              width: "100%", padding: "5px 6px", border: "none", borderRadius: 6,
              background: active ? "var(--surface-sunken)" : "transparent",
              cursor: onSelect ? "pointer" : "default", textAlign: "left", color: "inherit",
            }}
          >
            <span style={{ fontSize: 12, fontWeight: 600, overflow: "hidden",
                           textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}>
              <span style={{ color: "var(--ink-muted)", marginRight: 5 }}>{family.abbr}</span>
              {family.name}
            </span>
            <span className="bar-track">
              <span className="bar-fill" style={{
                width: `${pct}%`,
                background: complete ? "var(--status-good)" : "var(--accent)",
              }} />
            </span>
            <span style={{ fontSize: 12, color: "var(--ink-secondary)", textAlign: "right",
                           whiteSpace: "nowrap" }}
                  className="mono">
              {family.met}/{family.total}
              {family.deducted_points > 0 ? (
                <span style={{ color: "var(--status-critical)", marginLeft: 6 }}>
                  −{family.deducted_points}
                </span>
              ) : null}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** How the 110 requirements are recorded today. Stacked once, labelled beneath. */
export function StatusBreakdown({ byStatus, onSelect }: {
  byStatus: Record<string, number>;
  onSelect?: (status: ImplementationStatus) => void;
}) {
  const total = STATUS_ORDER.reduce((sum, status) => sum + (byStatus[status] ?? 0), 0) || 1;
  return (
    <div>
      <div style={{ display: "flex", height: 26, borderRadius: 6, overflow: "hidden", gap: 2 }}>
        {STATUS_ORDER.map((status) => {
          const count = byStatus[status] ?? 0;
          if (!count) return null;
          const meta = STATUS_META[status];
          return (
            <button
              key={status}
              type="button"
              onClick={() => onSelect?.(status)}
              title={`${meta.label}: ${count} requirement${count === 1 ? "" : "s"}`}
              aria-label={`${meta.label}: ${count}`}
              style={{
                width: `${(count / total) * 100}%`, background: meta.color,
                border: "none", padding: 0, cursor: onSelect ? "pointer" : "default",
                minWidth: 3,
              }}
            />
          );
        })}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px", marginTop: 11 }}>
        {STATUS_ORDER.map((status) => {
          const count = byStatus[status] ?? 0;
          const meta = STATUS_META[status];
          return (
            <span key={status} style={{
              display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12,
              color: count ? "var(--ink-secondary)" : "var(--ink-muted)",
            }}>
              <span style={{
                width: 9, height: 9, borderRadius: 2, background: meta.color,
                opacity: count ? 1 : 0.35,
              }} aria-hidden="true" />
              {meta.label}
              <strong className="mono" style={{ color: count ? "var(--ink)" : "inherit" }}>{count}</strong>
            </span>
          );
        })}
      </div>
    </div>
  );
}

interface TrendPoint { date: string; score: number; label: string }

/** Score over time. One series, so the card title names it and no legend box is needed. */
export function ScoreTrend({ snapshots }: { snapshots: ScoreSnapshot[] }) {
  if (snapshots.length < 2) {
    return (
      <p style={{ color: "var(--ink-muted)", fontSize: 13, margin: 0 }}>
        Take a snapshot now and again after your next round of remediation: the trend appears here
        and gives you something to show a prime contractor.
      </p>
    );
  }
  const data: TrendPoint[] = snapshots.map((snapshot) => ({
    date: snapshot.taken_at,
    score: snapshot.sprs_score,
    label: formatDate(snapshot.taken_at),
  }));
  const scores = data.map((point) => point.score);
  const low = Math.min(...scores, 80);
  const high = Math.max(...scores, 110);
  const pad = Math.max(6, Math.round((high - low) * 0.12));

  return (
    <div style={{ height: 210 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 6, right: 14, bottom: 0, left: -12 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: AXIS }} tickLine={false}
                 axisLine={{ stroke: GRID }} minTickGap={22} />
          <YAxis domain={[low - pad, high + pad]} tick={{ fontSize: 11, fill: AXIS }}
                 tickLine={false} axisLine={false} width={44} />
          <Tooltip
            cursor={{ stroke: AXIS, strokeDasharray: "3 3" }}
            contentStyle={{
              background: "var(--surface-raised)", border: "1px solid var(--line)",
              borderRadius: 8, fontSize: 12, color: "var(--ink)",
            }}
            labelStyle={{ color: "var(--ink-secondary)" }}
            formatter={(value) => [`${String(value)} of 110`, "SPRS score"] as [string, string]}
          />
          <Line type="monotone" dataKey="score" stroke="var(--accent)" strokeWidth={2}
                dot={{ r: 3, strokeWidth: 0, fill: "var(--accent)" }}
                activeDot={{ r: 5, strokeWidth: 2, stroke: "var(--surface-raised)" }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Coverage meter: a proportion with its own label, never a lone percentage. */
export function CoverageMeter({ label, covered, total, pct, hint }: {
  label: string; covered: number; total: number; pct: number; hint?: string;
}) {
  const tone = pct >= 80 ? "var(--status-good)" : pct >= 40 ? "var(--status-warning)" : "var(--status-critical)";
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
        <span style={{ fontWeight: 600 }}>{label}</span>
        <span className="mono" style={{ color: "var(--ink-secondary)" }}>
          {covered} / {total} &middot; {pct}%
        </span>
      </div>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${Math.min(100, pct)}%`, background: tone }} />
      </div>
      {hint ? <div className="field-hint">{hint}</div> : null}
    </div>
  );
}
