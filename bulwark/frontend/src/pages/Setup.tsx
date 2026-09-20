import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateSystem, useSaveOrganization, useSeedDemo } from "../api/hooks";
import { useSystem } from "../system";
import { useToast } from "../components/Toast";

export default function Setup() {
  const [step, setStep] = useState(0);
  const [org, setOrg] = useState({
    name: "", cage_code: "", uei: "", city: "", state: "",
    industry: "", employee_count: "",
    primary_contact_name: "", primary_contact_email: "",
    it_contact_name: "", it_contact_email: "",
  });
  const [system, setSystemForm] = useState({
    name: "CUI Enclave", environment: "hybrid", description: "",
    cui_types: "", boundary_description: "",
  });

  const saveOrg = useSaveOrganization();
  const createSystem = useCreateSystem();
  const seedDemo = useSeedDemo();
  const { setSystemId } = useSystem();
  const navigate = useNavigate();
  const { notify } = useToast();

  function saveOrganization() {
    saveOrg.mutate(
      {
        ...org,
        employee_count: org.employee_count ? Number(org.employee_count) : null,
      },
      {
        onSuccess: () => setStep(1),
        onError: (error) => notify(error instanceof Error ? error.message : "Could not save", "error"),
      },
    );
  }

  function finish() {
    createSystem.mutate(system, {
      onSuccess: (created) => {
        setSystemId(created.id);
        notify("Your system is set up. All 110 requirements are ready to assess.");
        navigate("/");
      },
      onError: (error) => notify(error instanceof Error ? error.message : "Could not create", "error"),
    });
  }

  return (
    <div className="login-shell">
      <div className="card" style={{ maxWidth: 620, width: "100%" }}>
        <div className="card-body">
          <div className="stepper" aria-hidden="true">
            <span className={`step${step >= 0 ? " done" : ""}`} />
            <span className={`step${step >= 1 ? " done" : ""}`} />
          </div>

          {step === 0 ? (
            <>
              <h1>Who are you?</h1>
              <p style={{ color: "var(--ink-secondary)" }}>
                This goes on the cover of your system security plan and your SPRS submission.
              </p>

              <div className="grid grid-2" style={{ marginTop: 14 }}>
                <div className="field">
                  <label htmlFor="org-name">Company name</label>
                  <input id="org-name" type="text" value={org.name} autoFocus
                         onChange={(event) => setOrg({ ...org, name: event.target.value })} />
                </div>
                <div className="field">
                  <label htmlFor="org-industry">Industry</label>
                  <input id="org-industry" type="text" placeholder="Precision machining"
                         value={org.industry}
                         onChange={(event) => setOrg({ ...org, industry: event.target.value })} />
                </div>
                <div className="field">
                  <label htmlFor="org-cage">CAGE code</label>
                  <input id="org-cage" type="text" value={org.cage_code}
                         onChange={(event) => setOrg({ ...org, cage_code: event.target.value })} />
                </div>
                <div className="field">
                  <label htmlFor="org-uei">Unique Entity ID</label>
                  <input id="org-uei" type="text" value={org.uei}
                         onChange={(event) => setOrg({ ...org, uei: event.target.value })} />
                </div>
                <div className="field">
                  <label htmlFor="org-city">City</label>
                  <input id="org-city" type="text" value={org.city}
                         onChange={(event) => setOrg({ ...org, city: event.target.value })} />
                </div>
                <div className="field">
                  <label htmlFor="org-state">State</label>
                  <input id="org-state" type="text" value={org.state}
                         onChange={(event) => setOrg({ ...org, state: event.target.value })} />
                </div>
                <div className="field">
                  <label htmlFor="org-employees">Employees</label>
                  <input id="org-employees" type="number" min={1} value={org.employee_count}
                         onChange={(event) => setOrg({ ...org, employee_count: event.target.value })} />
                </div>
                <div className="field">
                  <label htmlFor="org-contact">Senior official</label>
                  <input id="org-contact" type="text" value={org.primary_contact_name}
                         onChange={(event) => setOrg({ ...org, primary_contact_name: event.target.value })} />
                </div>
                <div className="field">
                  <label htmlFor="org-contact-email">Senior official email</label>
                  <input id="org-contact-email" type="email" value={org.primary_contact_email}
                         onChange={(event) => setOrg({ ...org, primary_contact_email: event.target.value })} />
                </div>
                <div className="field">
                  <label htmlFor="org-it">IT contact</label>
                  <input id="org-it" type="text" value={org.it_contact_name}
                         onChange={(event) => setOrg({ ...org, it_contact_name: event.target.value })} />
                </div>
              </div>

              <div className="btn-row" style={{ justifyContent: "space-between", marginTop: 6 }}>
                <button type="button" className="btn-link"
                        onClick={() => seedDemo.mutate(undefined, {
                          onSuccess: () => { notify("Demo data loaded."); navigate("/"); },
                        })}
                        disabled={seedDemo.isPending}>
                  Or load the demo machine shop
                </button>
                <button type="button" className="btn btn-primary" onClick={saveOrganization}
                        disabled={!org.name || saveOrg.isPending}>
                  Continue
                </button>
              </div>
            </>
          ) : (
            <>
              <h1>What is in scope?</h1>
              <p style={{ color: "var(--ink-secondary)" }}>
                A system is one assessment scope: the people, endpoints, servers and cloud services
                that handle Controlled Unclassified Information. Most small suppliers have exactly one.
              </p>

              <div className="field" style={{ marginTop: 14 }}>
                <label htmlFor="sys-name">System name</label>
                <input id="sys-name" type="text" value={system.name} autoFocus
                       onChange={(event) => setSystemForm({ ...system, name: event.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="sys-env">Where it runs</label>
                <select id="sys-env" value={system.environment}
                        onChange={(event) => setSystemForm({ ...system, environment: event.target.value })}>
                  <option value="on_prem">On premises</option>
                  <option value="cloud">Cloud</option>
                  <option value="hybrid">Both</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="sys-cui">What CUI do you receive?</label>
                <input id="sys-cui" type="text"
                       placeholder="Controlled Technical Information: drawings and specifications"
                       value={system.cui_types}
                       onChange={(event) => setSystemForm({ ...system, cui_types: event.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="sys-boundary">Boundary</label>
                <textarea id="sys-boundary"
                          placeholder="Which network segments, servers and cloud tenants hold CUI, and what separates them from everything else."
                          value={system.boundary_description}
                          onChange={(event) => setSystemForm({ ...system, boundary_description: event.target.value })} />
                <div className="field-hint">
                  You can refine this later. It becomes section 2 of your system security plan.
                </div>
              </div>

              <div className="btn-row" style={{ justifyContent: "space-between" }}>
                <button type="button" className="btn" onClick={() => setStep(0)}>Back</button>
                <button type="button" className="btn btn-primary" onClick={finish}
                        disabled={!system.name || createSystem.isPending}>
                  {createSystem.isPending ? "Setting up…" : "Finish setup"}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
