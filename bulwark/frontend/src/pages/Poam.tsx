import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useCatalog, useCreatePoam, usePoam } from "../api/hooks";
import { useSystem } from "../system";
import {
  Card, EmptyState, ErrorState, PageHead, PoamBadge, RiskBadge, Spinner, WeightPill,
  daysUntil, formatDate,
} from "../components/ui";
import { useToast } from "../components/Toast";
import type { PoamStatus } from "../api/types";

const TABS: { value: string; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In progress" },
  { value: "completed", label: "Completed" },
  { value: "risk_accepted", label: "Risk accepted" },
  { value: "closed", label: "Closed" },
  { value: "", label: "All" },
];

export default function Poam() {
  const { systemId } = useSystem();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();

  const status = params.get("status") ?? "open";
  const controlFilter = params.get("control") ?? "";
  const overdueOnly = params.get("overdue") === "true";

  const query: Record<string, string> = {};
  if (status) query.status = status;
  if (controlFilter) query.control_id = controlFilter;
  if (overdueOnly) query.overdue = "true";

  const items = usePoam(systemId, query);

  function setFilter(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next, { replace: true });
  }

  if (items.isLoading) return <Spinner />;
  if (items.isError) return <ErrorState error={items.error} />;

  const rows = items.data ?? [];

  return (
    <>
      <PageHead
        title="Plan of action and milestones"
        actions={
          <button type="button" className="btn btn-primary" onClick={() => navigate("/poam/new")}>
            New item
          </button>
        }
      >
        Every weakness you know about, who owns it and when it closes. This is the document an
        assessor reads next to your system security plan.
      </PageHead>

      <div className="filters">
        {TABS.map((tab) => (
          <button key={tab.value} type="button"
                  className={`chip${status === tab.value ? " on" : ""}`}
                  onClick={() => setFilter("status", tab.value)}>
            {tab.label}
          </button>
        ))}
        <button type="button" className={`chip${overdueOnly ? " on" : ""}`}
                onClick={() => setFilter("overdue", overdueOnly ? "" : "true")}>
          Overdue only
        </button>
        {controlFilter ? (
          <button type="button" className="btn-link" onClick={() => setFilter("control", "")}>
            Clear requirement filter ({controlFilter})
          </button>
        ) : null}
        <span style={{ marginLeft: "auto", color: "var(--ink-secondary)", fontSize: 12 }}>
          {rows.length} item{rows.length === 1 ? "" : "s"}
        </span>
      </div>

      <Card bodyClass="table-wrap">
        {rows.length === 0 ? (
          <EmptyState>Nothing here. Weaknesses you record, and failing checks Bulwark
            finds, appear in this list.</EmptyState>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>ID</th><th>Weakness</th><th>Requirement</th>
                <th>Risk</th><th>Status</th><th>Owner</th>
                <th>Due</th><th className="num">Milestones</th><th>Source</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => {
                const days = daysUntil(item.scheduled_completion);
                const overdue = days !== null && days < 0
                  && (item.status === "open" || item.status === "in_progress");
                const done = item.milestones.filter((milestone) => milestone.completed_at).length;
                return (
                  <tr key={item.id} className="clickable" onClick={() => navigate(`/poam/${item.id}`)}>
                    <td className="mono">POA&amp;M-{item.id}</td>
                    <td><Link to={`/poam/${item.id}`} style={{ color: "inherit" }}>{item.title}</Link></td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <Link to={`/controls/${item.control_id}`}>{item.control_id}</Link>
                    </td>
                    <td><RiskBadge risk={item.risk_level} /></td>
                    <td><PoamBadge status={item.status} /></td>
                    <td>{item.owner ?? "—"}</td>
                    <td style={{ whiteSpace: "nowrap", color: overdue ? "var(--status-critical)" : undefined }}>
                      {formatDate(item.scheduled_completion)}
                      {overdue ? <div style={{ fontSize: 11 }}>{Math.abs(days)} days late</div> : null}
                    </td>
                    <td className="num mono">{done}/{item.milestones.length}</td>
                    <td style={{ fontSize: 12, color: "var(--ink-secondary)" }}>
                      {item.source === "agent" ? "Agent" : item.source.replace("_", " ")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}

export function PoamNew() {
  const { systemId } = useSystem();
  const [params] = useSearchParams();
  const catalog = useCatalog();
  const create = useCreatePoam(systemId ?? 0);
  const navigate = useNavigate();
  const { notify } = useToast();

  const [form, setForm] = useState({
    control_id: params.get("control") ?? "",
    title: "",
    weakness_description: "",
    owner: "",
    scheduled_completion: "",
    remediation_plan: "",
    resources_required: "",
    cost_estimate: "",
  });
  const [milestones, setMilestones] = useState<string[]>([""]);

  const control = useMemo(
    () => catalog.data?.controls.find((item) => item.id === form.control_id),
    [catalog.data, form.control_id],
  );

  function submit() {
    create.mutate(
      {
        ...form,
        scheduled_completion: form.scheduled_completion || null,
        milestones: milestones.filter((text) => text.trim())
          .map((description) => ({ description })),
      },
      {
        onSuccess: (item) => { notify("Item created."); navigate(`/poam/${item.id}`); },
        onError: (error) => notify(
          error instanceof Error ? error.message : "Could not create", "error"),
      },
    );
  }

  return (
    <>
      <PageHead title="New plan of action item"
                actions={<Link className="btn btn-sm" to="/poam">Cancel</Link>}>
        Record a weakness, who owns it and when it will be closed.
      </PageHead>

      <div style={{ maxWidth: 680 }}>
        <Card>
          <div className="field">
            <label htmlFor="poam-control">Requirement</label>
            <select id="poam-control" value={form.control_id}
                    onChange={(event) => setForm({ ...form, control_id: event.target.value })}>
              <option value="">Choose a requirement…</option>
              {(catalog.data?.controls ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.cmmc_id ?? item.id} — {item.name}
                </option>
              ))}
            </select>
            {control ? (
              <div className="field-hint">
                <WeightPill weight={control.weight} /> point value.{" "}
                {control.poam_never_allowed
                  ? "This requirement may never sit on a plan of action for a conditional certification."
                  : control.poam_allowed
                    ? "Eligible to remain on a plan of action."
                    : "Worth more than one point, so it must be closed before a conditional certification."}
              </div>
            ) : null}
          </div>

          <div className="field">
            <label htmlFor="poam-title">Weakness</label>
            <input id="poam-title" type="text" value={form.title}
                   placeholder="Roll out multifactor authentication to general users"
                   onChange={(event) => setForm({ ...form, title: event.target.value })} />
          </div>

          <div className="field">
            <label htmlFor="poam-desc">What exactly is missing</label>
            <textarea id="poam-desc" value={form.weakness_description}
                      onChange={(event) => setForm({ ...form, weakness_description: event.target.value })} />
          </div>

          <div className="grid grid-2">
            <div className="field">
              <label htmlFor="poam-owner">Owner</label>
              <input id="poam-owner" type="text" value={form.owner}
                     onChange={(event) => setForm({ ...form, owner: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="poam-due">Scheduled completion</label>
              <input id="poam-due" type="date" value={form.scheduled_completion}
                     onChange={(event) => setForm({ ...form, scheduled_completion: event.target.value })} />
            </div>
          </div>

          <div className="field">
            <label htmlFor="poam-plan">Remediation plan</label>
            <textarea id="poam-plan" value={form.remediation_plan}
                      onChange={(event) => setForm({ ...form, remediation_plan: event.target.value })} />
          </div>

          <div className="grid grid-2">
            <div className="field">
              <label htmlFor="poam-resources">Resources required</label>
              <input id="poam-resources" type="text" value={form.resources_required}
                     onChange={(event) => setForm({ ...form, resources_required: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="poam-cost">Estimated cost</label>
              <input id="poam-cost" type="text" placeholder="$4,000" value={form.cost_estimate}
                     onChange={(event) => setForm({ ...form, cost_estimate: event.target.value })} />
            </div>
          </div>

          <div className="field">
            <label>Milestones</label>
            {milestones.map((milestone, index) => (
              <input
                key={index}
                type="text"
                value={milestone}
                placeholder={`Step ${index + 1}`}
                style={{ marginBottom: 6 }}
                onChange={(event) => setMilestones((current) =>
                  current.map((value, position) => position === index ? event.target.value : value))}
              />
            ))}
            <button type="button" className="btn-link"
                    onClick={() => setMilestones((current) => [...current, ""])}>
              Add another milestone
            </button>
          </div>

          <div className="btn-row">
            <button type="button" className="btn btn-primary" onClick={submit}
                    disabled={!form.control_id || !form.title || create.isPending}>
              Create item
            </button>
          </div>
        </Card>
      </div>
    </>
  );
}

export const POAM_STATUSES: PoamStatus[] = [
  "open", "in_progress", "completed", "risk_accepted", "closed",
];
