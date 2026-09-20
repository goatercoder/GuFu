/** Small shared pieces: status badges, weight pills, page states, dialogs. */
import { useEffect, useState, type ReactNode } from "react";
import type { ImplementationStatus, ObjectiveStatus, PoamStatus, RiskLevel } from "../api/types";

/** Implementation status presentation. Colour is never the only signal: every badge has a label,
 *  and the icon glyph distinguishes them for colour-blind readers and in forced-colors mode. */
export const STATUS_META: Record<ImplementationStatus,
  { label: string; tone: string; color: string; icon: string }> = {
  implemented: { label: "Implemented", tone: "good", color: "var(--status-good)", icon: "✓" },
  partially_implemented: { label: "Partially", tone: "warning", color: "var(--status-warning)", icon: "◐" },
  planned: { label: "Planned", tone: "planned", color: "var(--status-planned)", icon: "◔" },
  not_implemented: { label: "Not implemented", tone: "critical", color: "var(--status-critical)", icon: "✗" },
  not_applicable: { label: "Not applicable", tone: "neutral", color: "var(--status-neutral)", icon: "–" },
};

export const STATUS_ORDER: ImplementationStatus[] = [
  "implemented", "partially_implemented", "planned", "not_implemented", "not_applicable",
];

export const OBJECTIVE_META: Record<ObjectiveStatus, { label: string; tone: string; icon: string }> = {
  met: { label: "Met", tone: "good", icon: "✓" },
  not_met: { label: "Not met", tone: "critical", icon: "✗" },
  not_applicable: { label: "N/A", tone: "neutral", icon: "–" },
  unknown: { label: "Not assessed", tone: "neutral", icon: "?" },
};

export const POAM_META: Record<PoamStatus, { label: string; tone: string; icon: string }> = {
  open: { label: "Open", tone: "critical", icon: "●" },
  in_progress: { label: "In progress", tone: "warning", icon: "◐" },
  completed: { label: "Completed", tone: "good", icon: "✓" },
  risk_accepted: { label: "Risk accepted", tone: "planned", icon: "!" },
  closed: { label: "Closed", tone: "neutral", icon: "–" },
};

export const RISK_META: Record<RiskLevel, { label: string; tone: string }> = {
  low: { label: "Low", tone: "neutral" },
  moderate: { label: "Moderate", tone: "warning" },
  high: { label: "High", tone: "critical" },
  critical: { label: "Critical", tone: "critical" },
};

export function StatusBadge({ status }: { status: ImplementationStatus }) {
  const meta = STATUS_META[status] ?? STATUS_META.not_implemented;
  return (
    <span className={`badge ${meta.tone}`}>
      <span aria-hidden="true">{meta.icon}</span>
      {meta.label}
    </span>
  );
}

export function ObjectiveBadge({ status }: { status: ObjectiveStatus }) {
  const meta = OBJECTIVE_META[status] ?? OBJECTIVE_META.unknown;
  return (
    <span className={`badge ${meta.tone}`}>
      <span aria-hidden="true">{meta.icon}</span>
      {meta.label}
    </span>
  );
}

export function PoamBadge({ status }: { status: PoamStatus }) {
  const meta = POAM_META[status] ?? POAM_META.open;
  return (
    <span className={`badge ${meta.tone}`}>
      <span aria-hidden="true">{meta.icon}</span>
      {meta.label}
    </span>
  );
}

export function RiskBadge({ risk }: { risk: RiskLevel }) {
  const meta = RISK_META[risk] ?? RISK_META.moderate;
  return <span className={`badge ${meta.tone}`}>{meta.label}</span>;
}

/** The DoD Assessment Methodology point value: what this requirement costs if it is not met. */
export function WeightPill({ weight }: { weight: number }) {
  return (
    <span className={`weight weight-${weight}`} title={`${weight}-point requirement`}>
      {weight}
    </span>
  );
}

export function CheckStatusBadge({ status }: { status: string }) {
  const map: Record<string, { tone: string; icon: string; label: string }> = {
    pass: { tone: "good", icon: "✓", label: "Pass" },
    fail: { tone: "critical", icon: "✗", label: "Fail" },
    error: { tone: "warning", icon: "!", label: "Error" },
    not_applicable: { tone: "neutral", icon: "–", label: "N/A" },
    info: { tone: "neutral", icon: "i", label: "Info" },
  };
  const meta = map[status] ?? { tone: "neutral", icon: "?", label: status };
  return (
    <span className={`badge ${meta.tone}`}>
      <span aria-hidden="true">{meta.icon}</span>
      {meta.label}
    </span>
  );
}

export const Spinner = () => <div className="spinner" role="status" aria-label="Loading" />;

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function ErrorState({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Something went wrong";
  return <div className="error-state">{message}</div>;
}

export function PageHead({ title, children, actions }:
  { title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div className="page-head-text">
        <h1>{title}</h1>
        {children ? <p>{children}</p> : null}
      </div>
      {actions ? <div className="btn-row">{actions}</div> : null}
    </div>
  );
}

export function Card({ title, note, actions, children, bodyClass }: {
  title?: string; note?: ReactNode; actions?: ReactNode;
  children: ReactNode; bodyClass?: string;
}) {
  return (
    <section className="card">
      {title ? (
        <header className="card-head">
          <h2>{title}</h2>
          {note ? <span className="card-note">{note}</span> : null}
          {actions}
        </header>
      ) : null}
      <div className={bodyClass ?? "card-body"}>{children}</div>
    </section>
  );
}

export function Confirm({ open, title, body, confirmLabel, onConfirm, onCancel, danger }: {
  open: boolean; title: string; body: ReactNode; confirmLabel?: string;
  onConfirm: () => void; onCancel: () => void; danger?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const handler = (event: KeyboardEvent) => { if (event.key === "Escape") onCancel(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onCancel]);

  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onCancel} role="presentation">
      <div className="modal" onClick={(event) => event.stopPropagation()} role="dialog"
           aria-modal="true" aria-label={title}>
        <div className="card-head"><h2>{title}</h2></div>
        <div className="card-body">
          <div style={{ marginBottom: 16 }}>{body}</div>
          <div className="btn-row" style={{ justifyContent: "flex-end" }}>
            <button type="button" className="btn" onClick={onCancel}>Cancel</button>
            <button type="button" className={danger ? "btn btn-danger" : "btn btn-primary"}
                    onClick={onConfirm}>
              {confirmLabel ?? "Confirm"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function CopyButton({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="btn btn-sm"
      onClick={() => {
        navigator.clipboard?.writeText(text).then(
          () => { setCopied(true); window.setTimeout(() => setCopied(false), 1600); },
          () => undefined,
        );
      }}
    >
      {copied ? "Copied" : (label ?? "Copy")}
    </button>
  );
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export function daysUntil(value: string | null | undefined): number | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return Math.ceil((date.getTime() - Date.now()) / 86_400_000);
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes && bytes !== 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/^./, (character) => character.toUpperCase());
}
