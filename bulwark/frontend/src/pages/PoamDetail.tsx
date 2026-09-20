import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  useAddMilestone, useDeleteMilestone, useDeletePoam, usePoamItem, useTransitionPoam,
  useUpdateMilestone, useUpdatePoam,
} from "../api/hooks";
import { useSystem } from "../system";
import {
  Card, Confirm, EmptyState, ErrorState, PageHead, PoamBadge, RiskBadge, Spinner,
  daysUntil, formatDate, formatDateTime, titleCase,
} from "../components/ui";
import { useToast } from "../components/Toast";
import type { PoamItem, PoamStatus, RiskLevel } from "../api/types";

const NEXT_STATUSES: Record<PoamStatus, PoamStatus[]> = {
  open: ["in_progress", "completed", "risk_accepted"],
  in_progress: ["open", "completed", "risk_accepted"],
  completed: ["closed", "in_progress"],
  risk_accepted: ["closed", "open", "in_progress"],
  closed: ["open"],
};

const RISKS: RiskLevel[] = ["low", "moderate", "high", "critical"];

export default function PoamDetail() {
  const { itemId } = useParams<{ itemId: string }>();
  const id = Number(itemId);
  const { systemId } = useSystem();
  const item = usePoamItem(id);
  const update = useUpdatePoam(systemId ?? 0);
  const transition = useTransitionPoam(systemId ?? 0);
  const remove = useDeletePoam(systemId ?? 0);
  const addMilestone = useAddMilestone(systemId ?? 0);
  const updateMilestone = useUpdateMilestone(systemId ?? 0, id);
  const deleteMilestone = useDeleteMilestone(systemId ?? 0, id);
  const navigate = useNavigate();
  const { notify } = useToast();

  const [form, setForm] = useState<Partial<PoamItem>>({});
  const [newMilestone, setNewMilestone] = useState("");
  const [note, setNote] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => { if (item.data) setForm(item.data); }, [item.data]);

  if (item.isLoading) return <Spinner />;
  if (item.isError) return <ErrorState error={item.error} />;
  if (!item.data) return <EmptyState>Item not found.</EmptyState>;

  const data = item.data;
  const days = daysUntil(data.scheduled_completion);
  const overdue = days !== null && days < 0
    && (data.status === "open" || data.status === "in_progress");
  const ageDays = data.identified_at
    ? Math.floor((Date.now() - new Date(data.identified_at).getTime()) / 86_400_000)
    : null;

  function save() {
    update.mutate(
      {
        itemId: id,
        body: {
          title: form.title,
          weakness_description: form.weakness_description ?? "",
          risk_level: form.risk_level,
          owner: form.owner ?? "",
          scheduled_completion: form.scheduled_completion || null,
          remediation_plan: form.remediation_plan ?? "",
          resources_required: form.resources_required ?? "",
          cost_estimate: form.cost_estimate ?? "",
        },
      },
      {
        onSuccess: () => notify("Saved."),
        onError: (error) => notify(error instanceof Error ? error.message : "Could not save", "error"),
      },
    );
  }

  return (
    <>
      <PageHead
        title={`POA&M-${data.id} — ${data.title}`}
        actions={
          <>
            <Link className="btn btn-sm" to={`/controls/${data.control_id}`}>
              Open {data.control_id}
            </Link>
            <Link className="btn btn-sm" to="/poam">Back</Link>
          </>
        }
      >
        Raised {formatDate(data.identified_at)} from {titleCase(data.source)}
        {data.check_id ? ` (check ${data.check_id})` : ""}.
      </PageHead>

      {overdue ? (
        <div className="callout bad" style={{ marginBottom: 14 }}>
          <strong>Overdue by {Math.abs(days ?? 0)} days.</strong> Either close it or reschedule it
          with a reason. An assessor reads slipped dates as a process problem.
        </div>
      ) : null}
      {ageDays !== null && ageDays > 180
        && (data.status === "open" || data.status === "in_progress") ? (
        <div className="callout warn" style={{ marginBottom: 14 }}>
          <strong>Open for {ageDays} days.</strong> A conditional CMMC status gives 180 days to close
          plan of action items.
        </div>
      ) : null}

      <div className="grid grid-2" style={{ alignItems: "start" }}>
        <Card title="Details">
          <div className="field">
            <label htmlFor="item-title">Weakness</label>
            <input id="item-title" type="text" value={form.title ?? ""}
                   onChange={(event) => setForm({ ...form, title: event.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="item-desc">What exactly is missing</label>
            <textarea id="item-desc" value={form.weakness_description ?? ""}
                      onChange={(event) => setForm({ ...form, weakness_description: event.target.value })} />
          </div>
          <div className="grid grid-2">
            <div className="field">
              <label htmlFor="item-risk">Risk</label>
              <select id="item-risk" value={form.risk_level ?? data.risk_level}
                      onChange={(event) => setForm({
                        ...form, risk_level: event.target.value as RiskLevel,
                      })}>
                {RISKS.map((risk) => <option key={risk} value={risk}>{titleCase(risk)}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="item-owner">Owner</label>
              <input id="item-owner" type="text" value={form.owner ?? ""}
                     onChange={(event) => setForm({ ...form, owner: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="item-due">Scheduled completion</label>
              <input id="item-due" type="date" value={form.scheduled_completion ?? ""}
                     onChange={(event) => setForm({ ...form, scheduled_completion: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="item-cost">Estimated cost</label>
              <input id="item-cost" type="text" value={form.cost_estimate ?? ""}
                     onChange={(event) => setForm({ ...form, cost_estimate: event.target.value })} />
            </div>
          </div>
          <div className="field">
            <label htmlFor="item-plan">Remediation plan</label>
            <textarea id="item-plan" value={form.remediation_plan ?? ""}
                      onChange={(event) => setForm({ ...form, remediation_plan: event.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="item-resources">Resources required</label>
            <input id="item-resources" type="text" value={form.resources_required ?? ""}
                   onChange={(event) => setForm({ ...form, resources_required: event.target.value })} />
          </div>
          <div className="btn-row">
            <button type="button" className="btn btn-primary" onClick={save} disabled={update.isPending}>
              Save
            </button>
            <button type="button" className="btn btn-danger btn-sm"
                    onClick={() => setConfirmDelete(true)}>
              Delete
            </button>
          </div>
        </Card>

        <div style={{ display: "grid", gap: 14 }}>
          <Card title="Status">
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}>
              <PoamBadge status={data.status} />
              <RiskBadge risk={data.risk_level} />
              {data.actual_completion ? (
                <span style={{ fontSize: 12, color: "var(--ink-secondary)" }}>
                  completed {formatDate(data.actual_completion)}
                </span>
              ) : null}
            </div>

            <div className="field">
              <label htmlFor="item-note">Note for the record (optional)</label>
              <input id="item-note" type="text" value={note} placeholder="Why it moved"
                     onChange={(event) => setNote(event.target.value)} />
            </div>

            <div className="btn-row">
              {NEXT_STATUSES[data.status].map((next) => (
                <button
                  key={next}
                  type="button"
                  className={next === "completed" ? "btn btn-primary btn-sm" : "btn btn-sm"}
                  disabled={transition.isPending}
                  onClick={() => transition.mutate(
                    { itemId: id, status: next, note: note || undefined },
                    {
                      onSuccess: () => { notify(`Moved to ${next.replace("_", " ")}.`); setNote(""); },
                      onError: (error) => notify(
                        error instanceof Error ? error.message : "Could not move", "error"),
                    },
                  )}
                >
                  Move to {next.replace("_", " ")}
                </button>
              ))}
            </div>
          </Card>

          <Card title="Milestones"
                note={`${data.milestones.filter((m) => m.completed_at).length} of ${data.milestones.length} done`}>
            {data.milestones.length === 0 ? (
              <EmptyState>No milestones yet.</EmptyState>
            ) : (
              <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {data.milestones.map((milestone) => (
                  <li key={milestone.id} style={{
                    display: "flex", gap: 9, alignItems: "flex-start",
                    padding: "7px 0", borderBottom: "1px solid var(--line)",
                  }}>
                    <input
                      type="checkbox"
                      checked={Boolean(milestone.completed_at)}
                      style={{ width: "auto", marginTop: 3 }}
                      aria-label={`Mark "${milestone.description}" complete`}
                      onChange={(event) => updateMilestone.mutate({
                        milestoneId: milestone.id, body: { completed: event.target.checked },
                      })}
                    />
                    <span style={{ flex: 1 }}>
                      <span style={{
                        textDecoration: milestone.completed_at ? "line-through" : undefined,
                        color: milestone.completed_at ? "var(--ink-muted)" : undefined,
                      }}>
                        {milestone.description}
                      </span>
                      <div style={{ fontSize: 11, color: "var(--ink-muted)" }}>
                        {milestone.due_date ? `due ${formatDate(milestone.due_date)}` : "no date"}
                        {milestone.completed_at
                          ? ` · done ${formatDate(milestone.completed_at)}` : ""}
                      </div>
                    </span>
                    <button type="button" className="btn-link"
                            style={{ color: "var(--ink-muted)" }}
                            onClick={() => deleteMilestone.mutate(milestone.id)}>
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="btn-row" style={{ marginTop: 12 }}>
              <input type="text" className="compact" style={{ flex: 1, minWidth: 180 }}
                     placeholder="Add a milestone" value={newMilestone}
                     onChange={(event) => setNewMilestone(event.target.value)} />
              <button type="button" className="btn btn-sm" disabled={!newMilestone.trim()}
                      onClick={() => addMilestone.mutate(
                        { itemId: id, body: { description: newMilestone } },
                        { onSuccess: () => setNewMilestone("") },
                      )}>
                Add
              </button>
            </div>
          </Card>

          {data.notes ? (
            <Card title="History">
              <pre className="snippet">{data.notes}</pre>
              <div className="card-note" style={{ marginTop: 8 }}>
                Last updated {formatDateTime(data.updated_at)}
              </div>
            </Card>
          ) : null}
        </div>
      </div>

      <Confirm
        open={confirmDelete}
        title="Delete this item?"
        body={<>POA&amp;M-{data.id} and its milestones will be removed. This cannot be undone.</>}
        confirmLabel="Delete"
        danger
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() => remove.mutate(id, {
          onSuccess: () => { notify("Item deleted."); navigate("/poam"); },
        })}
      />
    </>
  );
}
