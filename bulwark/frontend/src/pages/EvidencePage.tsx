import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useCatalog, useDeleteEvidence, useEvidence, useUploadEvidence } from "../api/hooks";
import { useSystem } from "../system";
import { api } from "../api/client";
import {
  Card, Confirm, EmptyState, ErrorState, PageHead, Spinner, formatBytes, formatDate, titleCase,
} from "../components/ui";
import { useToast } from "../components/Toast";
import type { EvidenceKind } from "../api/types";

const KINDS: EvidenceKind[] = [
  "policy", "procedure", "document", "screenshot", "config_export", "log", "attestation", "other",
];

export default function EvidencePage() {
  const { systemId } = useSystem();
  const [params, setParams] = useSearchParams();
  const catalog = useCatalog();
  const upload = useUploadEvidence(systemId ?? 0);
  const remove = useDeleteEvidence(systemId ?? 0);
  const { notify } = useToast();

  const kind = params.get("kind") ?? "";
  const control = params.get("control") ?? "";
  const source = params.get("source") ?? "";
  const expired = params.get("expired") ?? "";

  const query: Record<string, string> = {};
  if (kind) query.kind = kind;
  if (control) query.control_id = control;
  if (source) query.source = source;
  if (expired) query.expired = expired;

  const items = useEvidence(systemId, query);

  const [form, setForm] = useState({
    title: "", kind: "policy" as EvidenceKind, description: "",
    collected_at: "", expires_at: "", control_ids: [] as string[],
  });
  const [file, setFile] = useState<File | null>(null);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);

  function setFilter(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next, { replace: true });
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const data = new FormData();
    data.set("title", form.title);
    data.set("kind", form.kind);
    if (form.description) data.set("description", form.description);
    if (form.collected_at) data.set("collected_at", new Date(form.collected_at).toISOString());
    if (form.expires_at) data.set("expires_at", new Date(form.expires_at).toISOString());
    form.control_ids.forEach((id) => data.append("control_ids", id));
    if (file) data.set("file", file);

    upload.mutate(data, {
      onSuccess: () => {
        notify("Evidence stored.");
        setForm({ title: "", kind: "policy", description: "", collected_at: "", expires_at: "", control_ids: [] });
        setFile(null);
        setShowForm(false);
      },
      onError: (error) => notify(error instanceof Error ? error.message : "Upload failed", "error"),
    });
  }

  if (items.isLoading) return <Spinner />;
  if (items.isError) return <ErrorState error={items.error} />;

  const rows = items.data ?? [];

  return (
    <>
      <PageHead
        title="Evidence"
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setShowForm((value) => !value)}>
            {showForm ? "Close" : "Add evidence"}
          </button>
        }
      >
        Policies, procedures, screenshots and exports that prove what you claim, plus everything the
        agents collect for you. Expired items stop counting towards coverage.
      </PageHead>

      {showForm ? (
        <div style={{ marginBottom: 14 }}>
          <Card title="Add evidence">
            <form onSubmit={submit}>
              <div className="grid grid-2">
                <div className="field">
                  <label htmlFor="ev-title">Title</label>
                  <input id="ev-title" type="text" required value={form.title}
                         onChange={(event) => setForm({ ...form, title: event.target.value })} />
                </div>
                <div className="field">
                  <label htmlFor="ev-kind">Kind</label>
                  <select id="ev-kind" value={form.kind}
                          onChange={(event) => setForm({
                            ...form, kind: event.target.value as EvidenceKind,
                          })}>
                    {KINDS.map((value) => (
                      <option key={value} value={value}>{titleCase(value)}</option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="ev-collected">Collected</label>
                  <input id="ev-collected" type="date" value={form.collected_at}
                         onChange={(event) => setForm({ ...form, collected_at: event.target.value })} />
                </div>
                <div className="field">
                  <label htmlFor="ev-expires">Expires</label>
                  <input id="ev-expires" type="date" value={form.expires_at}
                         onChange={(event) => setForm({ ...form, expires_at: event.target.value })} />
                  <div className="field-hint">
                    Set one for anything that goes out of date, such as a training record or a scan.
                  </div>
                </div>
              </div>
              <div className="field">
                <label htmlFor="ev-desc">Description</label>
                <textarea id="ev-desc" value={form.description} style={{ minHeight: 60 }}
                          onChange={(event) => setForm({ ...form, description: event.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="ev-file">File (optional)</label>
                <input id="ev-file" type="file"
                       onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
              </div>
              <div className="field">
                <label htmlFor="ev-controls">Requirements it supports</label>
                <select id="ev-controls" multiple size={7} value={form.control_ids}
                        onChange={(event) => setForm({
                          ...form,
                          control_ids: Array.from(event.target.selectedOptions).map((o) => o.value),
                        })}>
                  {(catalog.data?.controls ?? []).map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.cmmc_id ?? item.id} — {item.name}
                    </option>
                  ))}
                </select>
                <div className="field-hint">Hold Ctrl or Command to pick several.</div>
              </div>
              <button type="submit" className="btn btn-primary" disabled={upload.isPending || !form.title}>
                {upload.isPending ? "Uploading…" : "Store evidence"}
              </button>
            </form>
          </Card>
        </div>
      ) : null}

      <div className="filters">
        <select className="compact" value={kind} aria-label="Filter by kind"
                onChange={(event) => setFilter("kind", event.target.value)}>
          <option value="">Any kind</option>
          {[...KINDS, "agent_check" as EvidenceKind].map((value) => (
            <option key={value} value={value}>{titleCase(value)}</option>
          ))}
        </select>
        <select className="compact" value={source} aria-label="Filter by source"
                onChange={(event) => setFilter("source", event.target.value)}>
          <option value="">Any source</option>
          <option value="manual">Uploaded</option>
          <option value="agent">Collected by an agent</option>
        </select>
        <button type="button" className={`chip${expired === "true" ? " on" : ""}`}
                onClick={() => setFilter("expired", expired === "true" ? "" : "true")}>
          Expired only
        </button>
        {control ? (
          <button type="button" className="btn-link" onClick={() => setFilter("control", "")}>
            Clear requirement filter ({control})
          </button>
        ) : null}
        <span style={{ marginLeft: "auto", color: "var(--ink-secondary)", fontSize: 12 }}>
          {rows.length} item{rows.length === 1 ? "" : "s"}
        </span>
      </div>

      <Card bodyClass="table-wrap">
        {rows.length === 0 ? (
          <EmptyState>No evidence matches these filters.</EmptyState>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Title</th><th>Kind</th><th>Source</th><th>Requirements</th>
                <th>Collected</th><th>Expires</th><th>Size</th><th />
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => {
                const controlIds = Array.from(new Set(item.links.map((link) => link.control_id)));
                return (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.title}</strong>
                      {item.description ? (
                        <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                          {item.description.slice(0, 120)}
                        </div>
                      ) : null}
                    </td>
                    <td><span className="pill">{titleCase(item.kind)}</span></td>
                    <td style={{ fontSize: 12 }}>
                      {item.source === "agent" ? (
                        <span className="badge planned">
                          <span aria-hidden="true">⟳</span>Agent
                        </span>
                      ) : "Uploaded"}
                    </td>
                    <td style={{ fontSize: 12 }}>
                      {controlIds.slice(0, 4).map((id) => (
                        <Link key={id} to={`/controls/${id}`} style={{ marginRight: 6 }}>{id}</Link>
                      ))}
                      {controlIds.length > 4 ? `+${controlIds.length - 4}` : null}
                      {controlIds.length === 0 ? <span style={{ color: "var(--ink-muted)" }}>—</span> : null}
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>{formatDate(item.collected_at)}</td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {item.expired ? (
                        <span className="badge critical">
                          <span aria-hidden="true">✗</span>Expired
                        </span>
                      ) : formatDate(item.expires_at)}
                    </td>
                    <td className="num mono">{formatBytes(item.size_bytes)}</td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {item.file_name ? (
                        <a href={api.url(`/evidence/${item.id}/download`)} className="btn btn-sm">
                          Download
                        </a>
                      ) : null}{" "}
                      <button type="button" className="btn-link" style={{ color: "var(--ink-muted)" }}
                              onClick={() => setConfirmId(item.id)}>
                        Delete
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>

      <Confirm
        open={confirmId !== null}
        title="Delete this evidence?"
        body="The record, its links and any stored file are removed. This cannot be undone."
        confirmLabel="Delete"
        danger
        onCancel={() => setConfirmId(null)}
        onConfirm={() => {
          if (confirmId !== null) {
            remove.mutate(confirmId, { onSuccess: () => notify("Evidence deleted.") });
          }
          setConfirmId(null);
        }}
      />
    </>
  );
}
