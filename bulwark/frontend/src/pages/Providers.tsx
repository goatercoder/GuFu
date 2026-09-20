import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  useApplyTemplate, useCatalog, useCreateProvider, useCrmTemplates, useDeleteProvider,
  useMatrix, useProvider, useProviders, useSaveMatrix, useUpdateProvider,
} from "../api/hooks";
import {
  Card, Confirm, EmptyState, ErrorState, PageHead, Spinner, WeightPill, titleCase,
} from "../components/ui";
import { useToast } from "../components/Toast";
import type { FedrampStatus, Provider, ProviderKind, ResponsibilityModel, ResponsibilityRow } from "../api/types";

const KINDS: ProviderKind[] = ["csp", "msp", "mssp", "other"];
const FEDRAMP: FedrampStatus[] = ["none", "li_saas", "low", "moderate", "high", "equivalent", "il4", "il5"];
const MODELS: ResponsibilityModel[] = ["customer", "shared", "provider", "not_covered"];

export function ProvidersList() {
  const providers = useProviders();
  const create = useCreateProvider();
  const remove = useDeleteProvider();
  const { notify } = useToast();
  const [showForm, setShowForm] = useState(false);
  const [confirmId, setConfirmId] = useState<number | null>(null);

  if (providers.isLoading) return <Spinner />;
  if (providers.isError) return <ErrorState error={providers.error} />;

  const rows = providers.data ?? [];

  return (
    <>
      <PageHead
        title="External service providers"
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setShowForm((value) => !value)}>
            {showForm ? "Close" : "Add provider"}
          </button>
        }
      >
        Your managed service provider and any cloud service that touches CUI. Record who does what
        for each requirement, because an assessor will ask and inheritance only counts when the
        provider's authorization actually covers your CUI.
      </PageHead>

      {showForm ? (
        <div style={{ marginBottom: 14 }}>
          <ProviderForm
            onCancel={() => setShowForm(false)}
            onSave={(body) => create.mutate(body, {
              onSuccess: () => { notify("Provider added."); setShowForm(false); },
            })}
          />
        </div>
      ) : null}

      {rows.length === 0 ? (
        <Card><EmptyState>No providers recorded yet.</EmptyState></Card>
      ) : (
        <div className="grid grid-2">
          {rows.map((provider) => (
            <Card key={provider.id}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <h2 style={{ flex: 1 }}>
                  <Link to={`/providers/${provider.id}`}>{provider.name}</Link>
                </h2>
                <span className="pill">{provider.kind.toUpperCase()}</span>
              </div>
              <p style={{ color: "var(--ink-secondary)", marginTop: 6 }}>
                {provider.service_description ?? "No service description recorded."}
              </p>
              <dl className="kv" style={{ marginTop: 10 }}>
                <dt>FedRAMP</dt>
                <dd>
                  {provider.fedramp_status === "none"
                    ? "Not authorized (nothing can be inherited)"
                    : titleCase(provider.fedramp_status)}
                </dd>
                <dt>Responsibility doc</dt><dd>{provider.crm_reference ?? "—"}</dd>
                <dt>Contact</dt><dd>{provider.contact ?? "—"}</dd>
              </dl>
              <div className="btn-row" style={{ marginTop: 12 }}>
                <Link className="btn btn-sm" to={`/providers/${provider.id}`}>
                  Responsibility matrix
                </Link>
                <button type="button" className="btn-link" style={{ color: "var(--ink-muted)" }}
                        onClick={() => setConfirmId(provider.id)}>
                  Delete
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Confirm
        open={confirmId !== null}
        title="Delete this provider?"
        body="Its responsibility matrix is removed and any requirement assigned to it returns to you."
        confirmLabel="Delete"
        danger
        onCancel={() => setConfirmId(null)}
        onConfirm={() => {
          if (confirmId !== null) remove.mutate(confirmId, { onSuccess: () => notify("Provider deleted.") });
          setConfirmId(null);
        }}
      />
    </>
  );
}

function ProviderForm({ provider, onCancel, onSave }: {
  provider?: Provider;
  onCancel: () => void;
  onSave: (body: Record<string, unknown>) => void;
}) {
  const [form, setForm] = useState({
    name: provider?.name ?? "",
    kind: provider?.kind ?? ("msp" as ProviderKind),
    service_description: provider?.service_description ?? "",
    fedramp_status: provider?.fedramp_status ?? ("none" as FedrampStatus),
    crm_reference: provider?.crm_reference ?? "",
    contact: provider?.contact ?? "",
  });

  return (
    <Card title={provider ? "Edit provider" : "New provider"}>
      <div className="grid grid-2">
        <div className="field">
          <label htmlFor="prov-name">Name</label>
          <input id="prov-name" type="text" value={form.name} autoFocus
                 onChange={(event) => setForm({ ...form, name: event.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="prov-kind">Kind</label>
          <select id="prov-kind" value={form.kind}
                  onChange={(event) => setForm({ ...form, kind: event.target.value as ProviderKind })}>
            {KINDS.map((value) => <option key={value} value={value}>{value.toUpperCase()}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="prov-fedramp">FedRAMP status</label>
          <select id="prov-fedramp" value={form.fedramp_status}
                  onChange={(event) => setForm({
                    ...form, fedramp_status: event.target.value as FedrampStatus,
                  })}>
            {FEDRAMP.map((value) => (
              <option key={value} value={value}>
                {value === "none" ? "Not authorized" : titleCase(value)}
              </option>
            ))}
          </select>
          <div className="field-hint">
            Inheritance requires an authorization that covers your CUI at the right impact level.
          </div>
        </div>
        <div className="field">
          <label htmlFor="prov-contact">Contact</label>
          <input id="prov-contact" type="text" value={form.contact}
                 onChange={(event) => setForm({ ...form, contact: event.target.value })} />
        </div>
      </div>
      <div className="field">
        <label htmlFor="prov-service">What they do for you</label>
        <textarea id="prov-service" style={{ minHeight: 60 }} value={form.service_description}
                  onChange={(event) => setForm({ ...form, service_description: event.target.value })} />
      </div>
      <div className="field">
        <label htmlFor="prov-crm">Responsibility document</label>
        <input id="prov-crm" type="text" value={form.crm_reference}
               placeholder="Contract exhibit or the provider's customer responsibility matrix"
               onChange={(event) => setForm({ ...form, crm_reference: event.target.value })} />
      </div>
      <div className="btn-row">
        <button type="button" className="btn btn-primary" disabled={!form.name}
                onClick={() => onSave(form)}>
          Save
        </button>
        <button type="button" className="btn" onClick={onCancel}>Cancel</button>
      </div>
    </Card>
  );
}

export function ProviderDetail() {
  const { providerId } = useParams<{ providerId: string }>();
  const id = Number(providerId);
  const provider = useProvider(id);
  const matrix = useMatrix(id);
  const catalog = useCatalog();
  const templates = useCrmTemplates();
  const saveMatrix = useSaveMatrix(id);
  const applyTemplate = useApplyTemplate(id);
  const updateProvider = useUpdateProvider();
  const { notify } = useToast();
  const navigate = useNavigate();

  const [edits, setEdits] = useState<Record<string, Partial<ResponsibilityRow>>>({});
  const [templateChoice, setTemplateChoice] = useState("");
  const [confirmTemplate, setConfirmTemplate] = useState(false);
  const [editing, setEditing] = useState(false);
  const [familyFilter, setFamilyFilter] = useState("");

  useEffect(() => { setEdits({}); }, [matrix.data]);

  const rows = useMemo(() => {
    const all = matrix.data ?? [];
    return familyFilter ? all.filter((row) => row.family_id === familyFilter) : all;
  }, [matrix.data, familyFilter]);

  if (provider.isLoading || matrix.isLoading) return <Spinner />;
  if (provider.isError) return <ErrorState error={provider.error} />;
  if (!provider.data) return <EmptyState>Provider not found.</EmptyState>;

  const changed = Object.keys(edits).length;
  const summary = (matrix.data ?? []).reduce<Record<string, number>>((acc, row) => {
    acc[row.model] = (acc[row.model] ?? 0) + 1;
    if (row.inherited) acc.inherited = (acc.inherited ?? 0) + 1;
    return acc;
  }, {});

  function commit() {
    const payload = Object.entries(edits).map(([controlId, patch]) => {
      const original = (matrix.data ?? []).find((row) => row.control_id === controlId);
      return {
        control_id: controlId,
        model: patch.model ?? original?.model ?? "not_covered",
        provider_responsibility: patch.provider_responsibility ?? original?.provider_responsibility ?? "",
        customer_responsibility: patch.customer_responsibility ?? original?.customer_responsibility ?? "",
        inherited: patch.inherited ?? original?.inherited ?? false,
      };
    });
    saveMatrix.mutate(payload, {
      onSuccess: () => { notify(`${payload.length} row(s) saved.`); setEdits({}); },
      onError: (error) => notify(error instanceof Error ? error.message : "Could not save", "error"),
    });
  }

  return (
    <>
      <PageHead
        title={provider.data.name}
        actions={
          <>
            <button type="button" className="btn btn-sm" onClick={() => setEditing((value) => !value)}>
              {editing ? "Close" : "Edit details"}
            </button>
            <Link className="btn btn-sm" to="/providers">Back</Link>
          </>
        }
      >
        {provider.data.service_description ?? "Record who is responsible for each requirement."}
      </PageHead>

      {editing ? (
        <div style={{ marginBottom: 14 }}>
          <ProviderForm
            provider={provider.data}
            onCancel={() => setEditing(false)}
            onSave={(body) => updateProvider.mutate({ providerId: id, body }, {
              onSuccess: () => { notify("Provider saved."); setEditing(false); },
            })}
          />
        </div>
      ) : null}

      <div className="grid grid-4" style={{ marginBottom: 14 }}>
        {(["provider", "shared", "customer", "not_covered"] as ResponsibilityModel[]).map((model) => (
          <Card key={model}><div className="tile">
            <div className="tile-label">{titleCase(model)}</div>
            <div className="tile-value">{summary[model] ?? 0}</div>
            <div className="tile-sub">
              {model === "provider" && summary.inherited
                ? `${summary.inherited} marked inherited` : "requirements"}
            </div>
          </div></Card>
        ))}
      </div>

      <div className="filters">
        <select className="compact" value={familyFilter} aria-label="Filter by family"
                onChange={(event) => setFamilyFilter(event.target.value)}>
          <option value="">All families</option>
          {(catalog.data?.families ?? []).map((family) => (
            <option key={family.id} value={family.id}>{family.abbr} — {family.name}</option>
          ))}
        </select>
        <select className="compact" value={templateChoice} aria-label="Apply a template"
                onChange={(event) => setTemplateChoice(event.target.value)}>
          <option value="">Apply a starting template…</option>
          {(templates.data ?? []).map((template) => (
            <option key={template.id} value={template.id}>{template.name}</option>
          ))}
        </select>
        <button type="button" className="btn btn-sm" disabled={!templateChoice}
                onClick={() => setConfirmTemplate(true)}>
          Apply
        </button>
        <div style={{ marginLeft: "auto" }} className="btn-row">
          {changed ? (
            <button type="button" className="btn btn-primary btn-sm" onClick={commit}
                    disabled={saveMatrix.isPending}>
              Save {changed} change{changed === 1 ? "" : "s"}
            </button>
          ) : null}
        </div>
      </div>

      <Card bodyClass="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Requirement</th><th className="num">Pts</th><th>Who</th>
              <th>Provider does</th><th>You do</th><th>Inherited</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const patch = edits[row.control_id] ?? {};
              const model = patch.model ?? row.model;
              return (
                <tr key={row.control_id}>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <Link to={`/controls/${row.control_id}`}>{row.cmmc_id ?? row.control_id}</Link>
                    <div style={{ fontSize: 11, color: "var(--ink-muted)" }}>{row.control_name}</div>
                  </td>
                  <td className="num"><WeightPill weight={row.weight} /></td>
                  <td>
                    <select className="compact" value={model}
                            aria-label={`Responsibility for ${row.control_id}`}
                            onChange={(event) => setEdits((current) => ({
                              ...current,
                              [row.control_id]: {
                                ...current[row.control_id],
                                model: event.target.value as ResponsibilityModel,
                              },
                            }))}>
                      {MODELS.map((value) => (
                        <option key={value} value={value}>{titleCase(value)}</option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <textarea
                      style={{ minHeight: 44, fontSize: 12 }}
                      aria-label={`What the provider does for ${row.control_id}`}
                      value={patch.provider_responsibility ?? row.provider_responsibility ?? ""}
                      onChange={(event) => setEdits((current) => ({
                        ...current,
                        [row.control_id]: {
                          ...current[row.control_id], provider_responsibility: event.target.value,
                        },
                      }))}
                    />
                  </td>
                  <td>
                    <textarea
                      style={{ minHeight: 44, fontSize: 12 }}
                      aria-label={`What you do for ${row.control_id}`}
                      value={patch.customer_responsibility ?? row.customer_responsibility ?? ""}
                      onChange={(event) => setEdits((current) => ({
                        ...current,
                        [row.control_id]: {
                          ...current[row.control_id], customer_responsibility: event.target.value,
                        },
                      }))}
                    />
                  </td>
                  <td style={{ textAlign: "center" }}>
                    <input
                      type="checkbox"
                      style={{ width: "auto" }}
                      aria-label={`Inherited for ${row.control_id}`}
                      checked={patch.inherited ?? row.inherited}
                      onChange={(event) => setEdits((current) => ({
                        ...current,
                        [row.control_id]: {
                          ...current[row.control_id], inherited: event.target.checked,
                        },
                      }))}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      <Confirm
        open={confirmTemplate}
        title="Apply this template?"
        body={
          <>
            Every row in the matrix is replaced with the template's starting position. Your own
            wording is overwritten. A template is a starting point: reconcile it against the
            provider's own responsibility documentation before you rely on it in an assessment.
          </>
        }
        confirmLabel="Apply template"
        onCancel={() => setConfirmTemplate(false)}
        onConfirm={() => {
          setConfirmTemplate(false);
          applyTemplate.mutate(templateChoice, {
            onSuccess: (response) => {
              notify(`${response.applied} rows applied from ${response.template_name}.`);
              setTemplateChoice("");
              navigate(`/providers/${id}`);
            },
            onError: (error) => notify(
              error instanceof Error ? error.message : "Could not apply", "error"),
          });
        }}
      />
    </>
  );
}
