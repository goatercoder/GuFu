import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  useAssetChecks, useAssets, useCreateAsset, useDeleteAsset, useUpdateAsset,
} from "../api/hooks";
import { useSystem } from "../system";
import {
  Card, CheckStatusBadge, Confirm, EmptyState, ErrorState, PageHead, Spinner,
  formatDateTime, titleCase,
} from "../components/ui";
import { useToast } from "../components/Toast";
import type { Asset, AssetCategory, AssetType } from "../api/types";

const CATEGORIES: { value: AssetCategory; label: string; blurb: string }[] = [
  { value: "cui", label: "CUI asset",
    blurb: "Processes, stores or transmits CUI. Assessed against every applicable requirement." },
  { value: "security_protection", label: "Security protection asset",
    blurb: "Provides a security function for the CUI environment, such as a firewall or the MSP's management tooling." },
  { value: "contractor_risk_managed", label: "Contractor risk managed",
    blurb: "Not intended to handle CUI and managed by policy rather than assessed against every requirement." },
  { value: "specialized", label: "Specialized asset",
    blurb: "Government property, operational technology, test equipment or restricted systems such as a CNC controller." },
  { value: "out_of_scope", label: "Out of scope",
    blurb: "Cannot handle CUI and is separated from the CUI environment. Record why." },
];

const TYPES: AssetType[] = [
  "workstation", "server", "network_device", "mobile", "printer", "iot_ot",
  "cloud_service", "application", "removable_media", "facility", "other",
];

export default function Assets() {
  const { systemId } = useSystem();
  const assets = useAssets(systemId);
  const create = useCreateAsset(systemId ?? 0);
  const update = useUpdateAsset(systemId ?? 0);
  const remove = useDeleteAsset(systemId ?? 0);
  const { notify } = useToast();

  const [category, setCategory] = useState<string>("");
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<Asset | null>(null);
  const [creating, setCreating] = useState(false);
  const [checksFor, setChecksFor] = useState<number | null>(null);
  const [confirmId, setConfirmId] = useState<number | null>(null);

  const checks = useAssetChecks(checksFor);

  const rows = useMemo(() => {
    const term = search.trim().toLowerCase();
    return (assets.data ?? []).filter((asset) => {
      if (category && asset.category !== category) return false;
      if (!term) return true;
      return [asset.name, asset.os_name, asset.ip_address, asset.owner, asset.location]
        .some((value) => (value ?? "").toLowerCase().includes(term));
    });
  }, [assets.data, category, search]);

  if (assets.isLoading) return <Spinner />;
  if (assets.isError) return <ErrorState error={assets.error} />;

  const counts = CATEGORIES.map((item) => ({
    ...item,
    count: (assets.data ?? []).filter((asset) => asset.category === item.value).length,
  }));
  const needsReview = (assets.data ?? []).filter((asset) => asset.needs_review).length;

  return (
    <>
      <PageHead
        title="Assets and scope"
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
            Add asset
          </button>
        }
      >
        What an assessor will look at, and what you have excluded. Categorising every asset is how
        you draw the assessment boundary, and the categories go straight into your system security plan.
      </PageHead>

      {needsReview ? (
        <div className="callout warn" style={{ marginBottom: 14 }}>
          <strong>{needsReview} asset{needsReview === 1 ? " was" : "s were"} created automatically</strong>
          {" "}from an agent report. Confirm the category and write the rationale before relying on
          this inventory.
        </div>
      ) : null}

      <div className="grid grid-3" style={{ marginBottom: 14 }}>
        {counts.map((item) => (
          <Card key={item.value}>
            <button
              type="button"
              className="tile"
              style={{
                display: "block", width: "100%", textAlign: "left", background: "none",
                border: "none", cursor: "pointer", color: "inherit",
              }}
              onClick={() => setCategory(category === item.value ? "" : item.value)}
            >
              <div className="tile-label">
                {item.label}{category === item.value ? " · filtering" : ""}
              </div>
              <div className="tile-value">{item.count}</div>
              <div className="tile-sub" style={{ minHeight: 34 }}>{item.blurb}</div>
            </button>
          </Card>
        ))}
      </div>

      <div className="filters">
        <input className="compact" style={{ minWidth: 220 }} type="text" value={search}
               placeholder="Search name, address, owner or location"
               aria-label="Search assets"
               onChange={(event) => setSearch(event.target.value)} />
        {category ? (
          <button type="button" className="btn-link" onClick={() => setCategory("")}>
            Clear category filter
          </button>
        ) : null}
        <span style={{ marginLeft: "auto", color: "var(--ink-secondary)", fontSize: 12 }}>
          {rows.length} of {(assets.data ?? []).length}
        </span>
      </div>

      <Card bodyClass="table-wrap">
        {rows.length === 0 ? (
          <EmptyState>No assets yet. Add them here, or install an agent and let it report.</EmptyState>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Asset</th><th>Type</th><th>Category</th><th>Operating system</th>
                <th>Address</th><th>Owner</th><th>Agent</th><th />
              </tr>
            </thead>
            <tbody>
              {rows.map((asset) => (
                <tr key={asset.id}>
                  <td>
                    <strong>{asset.name}</strong>
                    {asset.needs_review ? (
                      <span className="badge warning" style={{ marginLeft: 6 }}>
                        <span aria-hidden="true">!</span>Review
                      </span>
                    ) : null}
                    {asset.location ? (
                      <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>{asset.location}</div>
                    ) : null}
                  </td>
                  <td style={{ fontSize: 12 }}>{titleCase(asset.asset_type)}</td>
                  <td>
                    <select
                      className="compact"
                      value={asset.category}
                      aria-label={`Category for ${asset.name}`}
                      onChange={(event) => update.mutate(
                        {
                          assetId: asset.id,
                          body: { category: event.target.value, needs_review: false },
                        },
                        { onSuccess: () => notify(`${asset.name} categorised.`) },
                      )}
                    >
                      {CATEGORIES.map((item) => (
                        <option key={item.value} value={item.value}>{item.label}</option>
                      ))}
                    </select>
                  </td>
                  <td style={{ fontSize: 12 }}>
                    {asset.os_name ?? "—"}
                    {asset.os_version ? (
                      <div style={{ color: "var(--ink-muted)" }}>{asset.os_version}</div>
                    ) : null}
                  </td>
                  <td className="mono" style={{ fontSize: 12 }}>{asset.ip_address ?? "—"}</td>
                  <td style={{ fontSize: 12 }}>{asset.owner ?? "—"}</td>
                  <td style={{ fontSize: 12, whiteSpace: "nowrap" }}>
                    {asset.agent_last_seen ? (
                      <button type="button" className="btn-link"
                              onClick={() => setChecksFor(checksFor === asset.id ? null : asset.id)}>
                        {formatDateTime(asset.agent_last_seen)}
                      </button>
                    ) : <span style={{ color: "var(--ink-muted)" }}>never</span>}
                  </td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <button type="button" className="btn-link" onClick={() => setEditing(asset)}>
                      Edit
                    </button>{" "}
                    <button type="button" className="btn-link" style={{ color: "var(--ink-muted)" }}
                            onClick={() => setConfirmId(asset.id)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {checksFor !== null ? (
        <div style={{ marginTop: 14 }}>
          <Card
            title={`Latest checks — ${(assets.data ?? []).find((a) => a.id === checksFor)?.name ?? ""}`}
            actions={<button type="button" className="btn btn-sm" onClick={() => setChecksFor(null)}>Close</button>}
            bodyClass="table-wrap"
          >
            {checks.isLoading ? <Spinner /> : (checks.data ?? []).length === 0 ? (
              <EmptyState>No check results for this asset.</EmptyState>
            ) : (
              <table className="data">
                <thead>
                  <tr><th>Check</th><th>Status</th><th>Observed</th><th>Expected</th><th>Requirements</th></tr>
                </thead>
                <tbody>
                  {(checks.data ?? []).map((result) => (
                    <tr key={result.id}>
                      <td className="mono" style={{ fontSize: 12 }}>{result.check_id}</td>
                      <td><CheckStatusBadge status={result.status} /></td>
                      <td style={{ fontSize: 12 }}>{result.observed || result.error || "—"}</td>
                      <td style={{ fontSize: 12, color: "var(--ink-muted)" }}>{result.expected ?? "—"}</td>
                      <td style={{ fontSize: 12 }}>
                        {result.control_ids.map((id) => (
                          <Link key={id} to={`/controls/${id}`} style={{ marginRight: 6 }}>{id}</Link>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
      ) : null}

      {(editing || creating) ? (
        <AssetForm
          asset={editing}
          onCancel={() => { setEditing(null); setCreating(false); }}
          onSave={(body) => {
            if (editing) {
              update.mutate({ assetId: editing.id, body }, {
                onSuccess: () => { notify("Asset saved."); setEditing(null); },
              });
            } else {
              create.mutate(body, {
                onSuccess: () => { notify("Asset added."); setCreating(false); },
              });
            }
          }}
        />
      ) : null}

      <Confirm
        open={confirmId !== null}
        title="Delete this asset?"
        body="Its check history and agent-collected evidence are removed too. Uploaded evidence is kept."
        confirmLabel="Delete"
        danger
        onCancel={() => setConfirmId(null)}
        onConfirm={() => {
          if (confirmId !== null) remove.mutate(confirmId, { onSuccess: () => notify("Asset deleted.") });
          setConfirmId(null);
        }}
      />
    </>
  );
}

function AssetForm({ asset, onCancel, onSave }: {
  asset: Asset | null;
  onCancel: () => void;
  onSave: (body: Record<string, unknown>) => void;
}) {
  const [form, setForm] = useState({
    name: asset?.name ?? "",
    asset_type: asset?.asset_type ?? ("workstation" as AssetType),
    category: asset?.category ?? ("cui" as AssetCategory),
    category_rationale: asset?.category_rationale ?? "",
    os_name: asset?.os_name ?? "",
    ip_address: asset?.ip_address ?? "",
    location: asset?.location ?? "",
    owner: asset?.owner ?? "",
    description: asset?.description ?? "",
  });
  const selected = CATEGORIES.find((item) => item.value === form.category);

  return (
    <div className="modal-backdrop" onClick={onCancel} role="presentation">
      <div className="modal" style={{ maxWidth: 560 }} role="dialog" aria-modal="true"
           onClick={(event) => event.stopPropagation()}>
        <div className="card-head"><h2>{asset ? "Edit asset" : "Add asset"}</h2></div>
        <div className="card-body">
          <div className="field">
            <label htmlFor="asset-name">Name</label>
            <input id="asset-name" type="text" value={form.name} autoFocus
                   onChange={(event) => setForm({ ...form, name: event.target.value })} />
          </div>
          <div className="grid grid-2">
            <div className="field">
              <label htmlFor="asset-type">Type</label>
              <select id="asset-type" value={form.asset_type}
                      onChange={(event) => setForm({
                        ...form, asset_type: event.target.value as AssetType,
                      })}>
                {TYPES.map((value) => (
                  <option key={value} value={value}>{titleCase(value)}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="asset-category">CMMC category</label>
              <select id="asset-category" value={form.category}
                      onChange={(event) => setForm({
                        ...form, category: event.target.value as AssetCategory,
                      })}>
                {CATEGORIES.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
            </div>
          </div>
          {selected ? <div className="field-hint" style={{ marginTop: -6 }}>{selected.blurb}</div> : null}

          <div className="field" style={{ marginTop: 12 }}>
            <label htmlFor="asset-rationale">Why this category</label>
            <textarea id="asset-rationale" style={{ minHeight: 60 }} value={form.category_rationale}
                      onChange={(event) => setForm({ ...form, category_rationale: event.target.value })} />
            <div className="field-hint">
              Required for anything specialized or out of scope: it appears in the SSP as your
              justification.
            </div>
          </div>

          <div className="grid grid-2">
            <div className="field">
              <label htmlFor="asset-os">Operating system</label>
              <input id="asset-os" type="text" value={form.os_name}
                     onChange={(event) => setForm({ ...form, os_name: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="asset-ip">Address</label>
              <input id="asset-ip" type="text" value={form.ip_address}
                     onChange={(event) => setForm({ ...form, ip_address: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="asset-location">Location</label>
              <input id="asset-location" type="text" value={form.location}
                     onChange={(event) => setForm({ ...form, location: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="asset-owner">Owner</label>
              <input id="asset-owner" type="text" value={form.owner}
                     onChange={(event) => setForm({ ...form, owner: event.target.value })} />
            </div>
          </div>

          <div className="btn-row" style={{ justifyContent: "flex-end" }}>
            <button type="button" className="btn" onClick={onCancel}>Cancel</button>
            <button type="button" className="btn btn-primary" disabled={!form.name}
                    onClick={() => onSave({ ...form, needs_review: false })}>
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
