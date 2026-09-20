import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useActivity, useDeleteSystem, useHealth, useOrganization, useSaveOrganization, useSeedDemo,
  useSystems, useUpdateSystem,
} from "../api/hooks";
import { useSystem } from "../system";
import {
  Card, Confirm, EmptyState, PageHead, Spinner, formatDateTime, titleCase,
} from "../components/ui";
import { useToast } from "../components/Toast";
import type { Environment, Organization, SystemRecord, SystemStatus } from "../api/types";

export default function Settings() {
  const { systemId } = useSystem();
  const organization = useOrganization();
  const systems = useSystems();
  const saveOrg = useSaveOrganization();
  const updateSystem = useUpdateSystem(systemId ?? 0);
  const deleteSystem = useDeleteSystem();
  const seed = useSeedDemo();
  const activity = useActivity();
  const health = useHealth();
  const { notify } = useToast();
  const navigate = useNavigate();

  const [org, setOrg] = useState<Partial<Organization>>({});
  const [system, setSystemForm] = useState<Partial<SystemRecord>>({});
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => { if (organization.data) setOrg(organization.data); }, [organization.data]);
  useEffect(() => {
    const current = (systems.data ?? []).find((item) => item.id === systemId);
    if (current) setSystemForm(current);
  }, [systems.data, systemId]);

  if (organization.isLoading) return <Spinner />;

  return (
    <>
      <PageHead title="Settings">
        Your organization details go on the cover of the system security plan. The system details
        define the assessment scope.
      </PageHead>

      <div className="grid grid-2" style={{ marginBottom: 14, alignItems: "start" }}>
        <Card title="Organization">
          <div className="grid grid-2">
            <div className="field">
              <label htmlFor="set-name">Company name</label>
              <input id="set-name" type="text" value={org.name ?? ""}
                     onChange={(event) => setOrg({ ...org, name: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="set-legal">Legal name</label>
              <input id="set-legal" type="text" value={org.legal_name ?? ""}
                     onChange={(event) => setOrg({ ...org, legal_name: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="set-cage">CAGE code</label>
              <input id="set-cage" type="text" value={org.cage_code ?? ""}
                     onChange={(event) => setOrg({ ...org, cage_code: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="set-uei">Unique Entity ID</label>
              <input id="set-uei" type="text" value={org.uei ?? ""}
                     onChange={(event) => setOrg({ ...org, uei: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="set-address">Address</label>
              <input id="set-address" type="text" value={org.address ?? ""}
                     onChange={(event) => setOrg({ ...org, address: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="set-city">City</label>
              <input id="set-city" type="text" value={org.city ?? ""}
                     onChange={(event) => setOrg({ ...org, city: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="set-state">State</label>
              <input id="set-state" type="text" value={org.state ?? ""}
                     onChange={(event) => setOrg({ ...org, state: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="set-zip">ZIP</label>
              <input id="set-zip" type="text" value={org.zip ?? ""}
                     onChange={(event) => setOrg({ ...org, zip: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="set-contact">Senior official</label>
              <input id="set-contact" type="text" value={org.primary_contact_name ?? ""}
                     onChange={(event) => setOrg({ ...org, primary_contact_name: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="set-contact-email">Senior official email</label>
              <input id="set-contact-email" type="email" value={org.primary_contact_email ?? ""}
                     onChange={(event) => setOrg({ ...org, primary_contact_email: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="set-it">Security contact</label>
              <input id="set-it" type="text" value={org.it_contact_name ?? ""}
                     onChange={(event) => setOrg({ ...org, it_contact_name: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="set-it-email">Security contact email</label>
              <input id="set-it-email" type="email" value={org.it_contact_email ?? ""}
                     onChange={(event) => setOrg({ ...org, it_contact_email: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="set-industry">Industry</label>
              <input id="set-industry" type="text" value={org.industry ?? ""}
                     onChange={(event) => setOrg({ ...org, industry: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="set-employees">Employees</label>
              <input id="set-employees" type="number" min={1} value={org.employee_count ?? ""}
                     onChange={(event) => setOrg({
                       ...org,
                       employee_count: event.target.value ? Number(event.target.value) : null,
                     })} />
            </div>
          </div>
          <button type="button" className="btn btn-primary" disabled={!org.name || saveOrg.isPending}
                  onClick={() => saveOrg.mutate(org as Record<string, unknown>, {
                    onSuccess: () => notify("Organization saved."),
                  })}>
            Save organization
          </button>
        </Card>

        <div style={{ display: "grid", gap: 14 }}>
          <Card title="System">
            <div className="field">
              <label htmlFor="sys-set-name">Name</label>
              <input id="sys-set-name" type="text" value={system.name ?? ""}
                     onChange={(event) => setSystemForm({ ...system, name: event.target.value })} />
            </div>
            <div className="grid grid-2">
              <div className="field">
                <label htmlFor="sys-set-env">Environment</label>
                <select id="sys-set-env" value={system.environment ?? "hybrid"}
                        onChange={(event) => setSystemForm({
                          ...system, environment: event.target.value as Environment,
                        })}>
                  <option value="on_prem">On premises</option>
                  <option value="cloud">Cloud</option>
                  <option value="hybrid">Both</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="sys-set-status">Status</label>
                <select id="sys-set-status" value={system.status ?? "active"}
                        onChange={(event) => setSystemForm({
                          ...system, status: event.target.value as SystemStatus,
                        })}>
                  <option value="draft">Draft</option>
                  <option value="active">Active</option>
                  <option value="retired">Retired</option>
                </select>
              </div>
            </div>
            <div className="field">
              <label htmlFor="sys-set-desc">Description</label>
              <textarea id="sys-set-desc" style={{ minHeight: 60 }} value={system.description ?? ""}
                        onChange={(event) => setSystemForm({ ...system, description: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="sys-set-cui">CUI types</label>
              <input id="sys-set-cui" type="text" value={system.cui_types ?? ""}
                     onChange={(event) => setSystemForm({ ...system, cui_types: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="sys-set-boundary">Authorization boundary</label>
              <textarea id="sys-set-boundary" value={system.boundary_description ?? ""}
                        onChange={(event) => setSystemForm({
                          ...system, boundary_description: event.target.value,
                        })} />
            </div>
            <div className="field">
              <label htmlFor="sys-set-cui-desc">How CUI is handled</label>
              <textarea id="sys-set-cui-desc" value={system.cui_description ?? ""}
                        onChange={(event) => setSystemForm({
                          ...system, cui_description: event.target.value,
                        })} />
            </div>
            <div className="field">
              <label htmlFor="sys-set-flows">Data flows</label>
              <textarea id="sys-set-flows" value={system.data_flow_description ?? ""}
                        onChange={(event) => setSystemForm({
                          ...system, data_flow_description: event.target.value,
                        })} />
              <div className="field-hint">
                These three fields become sections 2 and 3 of your system security plan.
              </div>
            </div>
            <div className="btn-row">
              <button type="button" className="btn btn-primary" disabled={updateSystem.isPending}
                      onClick={() => updateSystem.mutate(system as Record<string, unknown>, {
                        onSuccess: () => notify("System saved."),
                      })}>
                Save system
              </button>
              <button type="button" className="btn btn-danger btn-sm"
                      onClick={() => setConfirmDelete(true)}>
                Delete system
              </button>
            </div>
          </Card>

          <Card title="Demo data">
            <p style={{ color: "var(--ink-secondary)", marginTop: 0 }}>
              Loads a 41-person machine shop part-way through readiness: twelve assets across every
              CMMC category, two providers with responsibility matrices, a plan of action, evidence
              and two endpoints reporting, one of them badly configured. Safe to run twice.
            </p>
            <button type="button" className="btn" disabled={seed.isPending}
                    onClick={() => seed.mutate(undefined, {
                      onSuccess: () => notify("Demo data loaded."),
                    })}>
              {seed.isPending ? "Loading…" : "Load demo data"}
            </button>
          </Card>

          <Card title="About">
            <dl className="kv">
              <dt>Version</dt><dd>{health.data?.version ?? "—"}</dd>
              <dt>Systems</dt><dd>{(systems.data ?? []).length}</dd>
            </dl>
          </Card>
        </div>
      </div>

      <Card title="Recent activity" bodyClass="table-wrap">
        {activity.isLoading ? <Spinner /> : (activity.data ?? []).length === 0 ? (
          <EmptyState>Nothing recorded yet.</EmptyState>
        ) : (
          <table className="data">
            <thead><tr><th>When</th><th>Who</th><th>Action</th><th>What</th></tr></thead>
            <tbody>
              {(activity.data ?? []).slice(0, 60).map((entry) => (
                <tr key={entry.id}>
                  <td style={{ whiteSpace: "nowrap" }}>{formatDateTime(entry.created_at)}</td>
                  <td>{entry.actor}</td>
                  <td><span className="pill">{titleCase(entry.action)}</span></td>
                  <td>{entry.summary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Confirm
        open={confirmDelete}
        title="Delete this system?"
        body="Every requirement record, plan of action item, evidence record, asset and agent report for this system is deleted. This cannot be undone."
        confirmLabel="Delete system"
        danger
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() => {
          setConfirmDelete(false);
          if (systemId) {
            deleteSystem.mutate(systemId, {
              onSuccess: () => { notify("System deleted."); navigate("/"); },
            });
          }
        }}
      />
    </>
  );
}
