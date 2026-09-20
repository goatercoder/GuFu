import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  useControlDetail, useEvidence, useLinkEvidence, useProviders, useUpdateImplementation,
  useUpdateObjectives,
} from "../api/hooks";
import { useSystem } from "../system";
import { api } from "../api/client";
import {
  Card, CheckStatusBadge, EmptyState, ErrorState, PageHead, PoamBadge, Spinner,
  STATUS_META, STATUS_ORDER, WeightPill, formatDate, formatDateTime, titleCase,
} from "../components/ui";
import { useToast } from "../components/Toast";
import type {
  Implementation, ObjectiveStatus, PartialCredit, Responsibility,
} from "../api/types";

const OBJECTIVE_OPTIONS: ObjectiveStatus[] = ["unknown", "met", "not_met", "not_applicable"];
const RESPONSIBILITY_OPTIONS: Responsibility[] = ["customer", "shared", "provider", "inherited"];

export default function ControlDetail() {
  const { controlId } = useParams<{ controlId: string }>();
  const { systemId } = useSystem();
  const detail = useControlDetail(systemId, controlId);
  const providers = useProviders();
  const update = useUpdateImplementation(systemId ?? 0);
  const saveObjectives = useUpdateObjectives(systemId ?? 0, controlId ?? "");
  const evidence = useEvidence(systemId);
  const linkEvidence = useLinkEvidence(systemId ?? 0);
  const { notify } = useToast();
  const navigate = useNavigate();

  const [form, setForm] = useState<Partial<Implementation>>({});
  const [objectiveEdits, setObjectiveEdits] = useState<Record<string, ObjectiveStatus>>({});
  const [linkChoice, setLinkChoice] = useState("");
  const [showDiscussion, setShowDiscussion] = useState(false);

  useEffect(() => {
    if (detail.data) {
      setForm(detail.data.implementation);
      setObjectiveEdits({});
    }
  }, [detail.data]);

  const unlinked = useMemo(() => {
    const linkedIds = new Set((detail.data?.evidence ?? []).map((item) => item.id));
    return (evidence.data ?? []).filter((item) => !linkedIds.has(item.id));
  }, [evidence.data, detail.data]);

  if (detail.isLoading) return <Spinner />;
  if (detail.isError) return <ErrorState error={detail.error} />;
  if (!detail.data) return <EmptyState>Requirement not found.</EmptyState>;

  const { control, implementation, objectives, objective_counts: counts } = detail.data;
  const guidance = control.guidance ?? {};
  const supportsPartialCredit = control.id === "3.5.3" || control.id === "3.13.11";

  function saveImplementation() {
    const body: Record<string, unknown> = {
      status: form.status,
      responsibility: form.responsibility,
      provider_id: form.provider_id ?? null,
      implementation_narrative: form.implementation_narrative ?? "",
      customer_responsibility: form.customer_responsibility ?? "",
      provider_responsibility: form.provider_responsibility ?? "",
      na_justification: form.na_justification ?? "",
      partial_credit: form.partial_credit ?? "none",
      assessed_by: form.assessed_by ?? "",
    };
    update.mutate({ controlId: control.id, body }, {
      onSuccess: () => notify("Saved."),
      onError: (error) => notify(error instanceof Error ? error.message : "Could not save", "error"),
    });
  }

  function saveObjectiveChanges() {
    const payload = Object.entries(objectiveEdits).map(([objective_id, status]) => ({
      objective_id, status,
    }));
    if (!payload.length) return;
    saveObjectives.mutate(payload, {
      onSuccess: () => { notify(`${payload.length} objective(s) updated.`); setObjectiveEdits({}); },
      onError: (error) => notify(error instanceof Error ? error.message : "Could not save", "error"),
    });
  }

  return (
    <>
      <PageHead
        title={`${control.cmmc_id ?? control.id} — ${control.name}`}
        actions={<Link className="btn btn-sm" to="/controls">Back to list</Link>}
      >
        {control.family_abbr} {control.family_name} &middot; {titleCase(control.requirement_type ?? "")}
        {" requirement"}
      </PageHead>

      <div className="grid grid-2" style={{ marginBottom: 14, alignItems: "start" }}>
        <div style={{ display: "grid", gap: 14 }}>
          <Card
            title="The requirement"
            note={<span><WeightPill weight={control.weight} /> point value</span>}
          >
            <p style={{ fontSize: 15, lineHeight: 1.55 }}>{control.statement}</p>
            {control.partial_credit ? (
              <div className="callout warn" style={{ marginTop: 8 }}>
                <strong>Partial credit available.</strong> {control.partial_credit.condition}:
                {" "}{control.partial_credit.deduction} points are deducted instead of {control.weight}.
              </div>
            ) : null}
            {control.poam_never_allowed ? (
              <div className="callout bad" style={{ marginTop: 8 }}>
                This requirement may never sit on a plan of action. It must be fully met before a
                conditional certification is possible.
              </div>
            ) : null}
            <button type="button" className="btn-link" style={{ marginTop: 10 }}
                    onClick={() => setShowDiscussion((value) => !value)}>
              {showDiscussion ? "Hide" : "Show"} the NIST discussion
            </button>
            {showDiscussion ? (
              <p style={{ color: "var(--ink-secondary)", marginTop: 8, lineHeight: 1.6 }}>
                {control.discussion}
              </p>
            ) : null}
            {control.nist_800_53?.length ? (
              <div className="card-note" style={{ marginTop: 10 }}>
                Derived from SP 800-53: {control.nist_800_53.join(", ")}
              </div>
            ) : null}
          </Card>

          {guidance.summary ? (
            <Card title="What this means for you">
              <p>{guidance.summary}</p>
              {guidance.machine_shop_example ? (
                <>
                  <h3 style={{ marginTop: 14, marginBottom: 4 }}>What good looks like</h3>
                  <p style={{ color: "var(--ink-secondary)" }}>{guidance.machine_shop_example}</p>
                </>
              ) : null}
              {guidance.remediation_steps?.length ? (
                <>
                  <h3 style={{ marginTop: 14, marginBottom: 4 }}>How to get there</h3>
                  <ol style={{ margin: 0, paddingLeft: 20, color: "var(--ink-secondary)" }}>
                    {guidance.remediation_steps.map((step) => <li key={step}>{step}</li>)}
                  </ol>
                </>
              ) : null}
              {guidance.typical_evidence?.length ? (
                <>
                  <h3 style={{ marginTop: 14, marginBottom: 4 }}>Evidence an assessor accepts</h3>
                  <ul style={{ margin: 0, paddingLeft: 20, color: "var(--ink-secondary)" }}>
                    {guidance.typical_evidence.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </>
              ) : null}
              {guidance.common_gaps?.length ? (
                <>
                  <h3 style={{ marginTop: 14, marginBottom: 4 }}>Where small shops slip</h3>
                  <ul style={{ margin: 0, paddingLeft: 20, color: "var(--ink-secondary)" }}>
                    {guidance.common_gaps.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </>
              ) : null}
            </Card>
          ) : null}

          <Card title="How it is assessed" note="NIST SP 800-171A">
            <dl className="kv">
              {control.assessment.examine ? (
                <><dt>Examine</dt><dd>{control.assessment.examine}</dd></>
              ) : null}
              {control.assessment.interview ? (
                <><dt>Interview</dt><dd>{control.assessment.interview}</dd></>
              ) : null}
              {control.assessment.test ? (
                <><dt>Test</dt><dd>{control.assessment.test}</dd></>
              ) : null}
            </dl>
          </Card>
        </div>

        <div style={{ display: "grid", gap: 14 }}>
          <Card title="Your implementation" note={detail.data.warnings.length
            ? <span style={{ color: "var(--status-warning)" }}>{detail.data.warnings[0]}</span>
            : undefined}>
            <div className="field">
              <label htmlFor="impl-status">Status</label>
              <select id="impl-status" value={form.status ?? implementation.status}
                      onChange={(event) => setForm({
                        ...form, status: event.target.value as Implementation["status"],
                      })}>
                {STATUS_ORDER.map((value) => (
                  <option key={value} value={value}>{STATUS_META[value].label}</option>
                ))}
              </select>
            </div>

            {supportsPartialCredit ? (
              <div className="field">
                <label htmlFor="impl-partial">Partial credit</label>
                <select id="impl-partial" value={form.partial_credit ?? implementation.partial_credit}
                        onChange={(event) => setForm({
                          ...form, partial_credit: event.target.value as PartialCredit,
                        })}>
                  <option value="none">None</option>
                  {control.id === "3.5.3" ? (
                    <option value="mfa_partial">
                      Multifactor for remote and privileged users only (deducts 3, not 5)
                    </option>
                  ) : (
                    <option value="encryption_non_fips">
                      Encryption in use but not FIPS-validated (deducts 3, not 5)
                    </option>
                  )}
                </select>
              </div>
            ) : null}

            <div className="field">
              <label htmlFor="impl-resp">Who is responsible</label>
              <select id="impl-resp" value={form.responsibility ?? implementation.responsibility}
                      onChange={(event) => setForm({
                        ...form, responsibility: event.target.value as Responsibility,
                      })}>
                {RESPONSIBILITY_OPTIONS.map((value) => (
                  <option key={value} value={value}>{titleCase(value)}</option>
                ))}
              </select>
            </div>

            {(form.responsibility ?? implementation.responsibility) !== "customer" ? (
              <div className="field">
                <label htmlFor="impl-provider">Provider</label>
                <select id="impl-provider" value={form.provider_id ?? implementation.provider_id ?? ""}
                        onChange={(event) => setForm({
                          ...form, provider_id: event.target.value ? Number(event.target.value) : null,
                        })}>
                  <option value="">Not set</option>
                  {(providers.data ?? []).map((provider) => (
                    <option key={provider.id} value={provider.id}>{provider.name}</option>
                  ))}
                </select>
                {detail.data.responsibility_row ? (
                  <div className="field-hint">
                    Matrix says: <strong>{detail.data.responsibility_row.model}</strong>
                    {detail.data.responsibility_row.inherited ? " (inherited)" : ""}
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="field">
              <label htmlFor="impl-narrative">How you implement it</label>
              <textarea id="impl-narrative"
                        placeholder="Write what you actually do. This becomes the requirement's paragraph in your system security plan."
                        value={form.implementation_narrative ?? ""}
                        onChange={(event) => setForm({
                          ...form, implementation_narrative: event.target.value,
                        })} />
            </div>

            {(form.status ?? implementation.status) === "not_applicable" ? (
              <div className="field">
                <label htmlFor="impl-na">Why it does not apply</label>
                <textarea id="impl-na" value={form.na_justification ?? ""}
                          onChange={(event) => setForm({ ...form, na_justification: event.target.value })} />
                <div className="field-hint">
                  An assessor will ask. Say what is absent from your environment and how you know.
                </div>
              </div>
            ) : null}

            <div className="field">
              <label htmlFor="impl-assessor">Assessed by</label>
              <input id="impl-assessor" type="text" value={form.assessed_by ?? ""}
                     onChange={(event) => setForm({ ...form, assessed_by: event.target.value })} />
              {implementation.assessed_at ? (
                <div className="field-hint">Last assessed {formatDate(implementation.assessed_at)}</div>
              ) : null}
            </div>

            <div className="btn-row">
              <button type="button" className="btn btn-primary" onClick={saveImplementation}
                      disabled={update.isPending}>
                {update.isPending ? "Saving…" : "Save"}
              </button>
              <button type="button" className="btn btn-sm"
                      onClick={() => navigate(`/poam/new?control=${control.id}`)}>
                Add to plan of action
              </button>
            </div>
          </Card>

          <Card title="Assessment objectives"
                note={`${counts.met + counts.not_applicable} of ${counts.total} met`}>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr><th>Objective</th><th>Determination statement</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {objectives.map((objective) => {
                    const value = objectiveEdits[objective.objective_id] ?? objective.status;
                    return (
                      <tr key={objective.objective_id}>
                        <td className="mono" style={{ whiteSpace: "nowrap" }}>{objective.objective_id}</td>
                        <td>{objective.text}</td>
                        <td>
                          <select
                            className="compact"
                            value={value}
                            aria-label={`Status for ${objective.objective_id}`}
                            onChange={(event) => setObjectiveEdits((current) => ({
                              ...current,
                              [objective.objective_id]: event.target.value as ObjectiveStatus,
                            }))}
                          >
                            {OBJECTIVE_OPTIONS.map((option) => (
                              <option key={option} value={option}>
                                {option === "unknown" ? "Not assessed" : titleCase(option)}
                              </option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="btn-row" style={{ marginTop: 12 }}>
              <button type="button" className="btn btn-primary btn-sm"
                      disabled={!Object.keys(objectiveEdits).length || saveObjectives.isPending}
                      onClick={saveObjectiveChanges}>
                Save {Object.keys(objectiveEdits).length || ""} objective change
                {Object.keys(objectiveEdits).length === 1 ? "" : "s"}
              </button>
              <button type="button" className="btn btn-sm"
                      onClick={() => setObjectiveEdits(Object.fromEntries(
                        objectives.map((objective) => [objective.objective_id, "met" as ObjectiveStatus]),
                      ))}>
                Mark all met
              </button>
            </div>
          </Card>
        </div>
      </div>

      <div className="grid grid-3">
        <Card title="Evidence" note={`${detail.data.evidence.length} linked`}>
          {detail.data.evidence.length === 0 ? (
            <EmptyState>Nothing attached yet.</EmptyState>
          ) : (
            <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none" }}>
              {detail.data.evidence.map((item) => (
                <li key={item.id} style={{ padding: "7px 0", borderBottom: "1px solid var(--line)" }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                    <strong style={{ flex: 1 }}>{item.title}</strong>
                    {item.file_name ? (
                      <a href={api.url(`/evidence/${item.id}/download`)}>Download</a>
                    ) : null}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                    <span className="pill">{titleCase(item.kind)}</span>{" "}
                    {item.source === "agent" ? "collected automatically" : "uploaded"}
                    {" · "}{formatDate(item.collected_at)}
                    {item.expired ? (
                      <span style={{ color: "var(--status-critical)" }}> · expired</span>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
          <div className="btn-row" style={{ marginTop: 12 }}>
            <select className="compact" value={linkChoice} aria-label="Link existing evidence"
                    onChange={(event) => setLinkChoice(event.target.value)}>
              <option value="">Link existing evidence…</option>
              {unlinked.map((item) => (
                <option key={item.id} value={item.id}>{item.title}</option>
              ))}
            </select>
            <button type="button" className="btn btn-sm" disabled={!linkChoice}
                    onClick={() => linkEvidence.mutate(
                      { evidenceId: Number(linkChoice), controlId: control.id },
                      {
                        onSuccess: () => { notify("Linked."); setLinkChoice(""); detail.refetch(); },
                        onError: (error) => notify(
                          error instanceof Error ? error.message : "Could not link", "error"),
                      },
                    )}>
              Link
            </button>
            <Link className="btn btn-sm" to="/evidence">Upload new</Link>
          </div>
        </Card>

        <Card title="Automated checks"
              note={control.check_ids.length ? `${control.check_ids.length} mapped` : "none mapped"}>
          {detail.data.check_results.length === 0 ? (
            <EmptyState>
              {control.check_ids.length
                ? "Mapped to a check, but no endpoint has reported yet."
                : "No automated check can prove this requirement. It needs a document or an attestation."}
            </EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead><tr><th>Check</th><th>Status</th><th>Observed</th></tr></thead>
                <tbody>
                  {detail.data.check_results.map((result) => (
                    <tr key={result.id}>
                      <td className="mono" style={{ fontSize: 12 }}>{result.check_id}</td>
                      <td><CheckStatusBadge status={result.status} /></td>
                      <td style={{ fontSize: 12, color: "var(--ink-secondary)" }}>
                        {result.observed || result.error || "—"}
                        <div style={{ color: "var(--ink-muted)" }}>
                          {formatDateTime(result.collected_at)}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Plan of action" note={`${detail.data.poam_items.length} item(s)`}>
          {detail.data.poam_items.length === 0 ? (
            <EmptyState>No open weaknesses recorded for this requirement.</EmptyState>
          ) : (
            <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none" }}>
              {detail.data.poam_items.map((item) => (
                <li key={item.id} style={{ padding: "7px 0", borderBottom: "1px solid var(--line)" }}>
                  <Link to={`/poam/${item.id}`}>{item.title}</Link>
                  <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 3 }}>
                    <PoamBadge status={item.status} />{" "}
                    {item.scheduled_completion ? `due ${formatDate(item.scheduled_completion)}` : ""}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
