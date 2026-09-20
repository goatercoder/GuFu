import { useState } from "react";
import { Link } from "react-router-dom";
import {
  useAgentStatus, useEnrollment, useFindings, useRotateKey, useUploadReport,
} from "../api/hooks";
import { useSystem } from "../system";
import {
  Card, Confirm, CopyButton, EmptyState, ErrorState, PageHead, Spinner, WeightPill,
  formatDateTime,
} from "../components/ui";
import { useToast } from "../components/Toast";

const PLATFORMS = [
  { key: "windows" as const, label: "Windows" },
  { key: "linux" as const, label: "Linux" },
  { key: "macos" as const, label: "macOS" },
];

export default function Agents() {
  const { systemId } = useSystem();
  const enrollment = useEnrollment(systemId);
  const status = useAgentStatus(systemId);
  const findings = useFindings(systemId);
  const rotate = useRotateKey(systemId ?? 0);
  const upload = useUploadReport(systemId ?? 0);
  const { notify } = useToast();

  const [platform, setPlatform] = useState<"windows" | "linux" | "macos">("windows");
  const [revealed, setRevealed] = useState(false);
  const [confirmRotate, setConfirmRotate] = useState(false);

  if (enrollment.isLoading) return <Spinner />;
  if (enrollment.isError) return <ErrorState error={enrollment.error} />;

  const info = enrollment.data;
  const agents = status.data ?? [];
  const failing = findings.data ?? [];
  const masked = info ? `${info.enrollment_key.slice(0, 4)}${"•".repeat(20)}` : "";

  return (
    <>
      <PageHead title="Evidence collection agents">
        Install the agent once on each machine and it proves your configuration every day, instead
        of you taking screenshots once a year. It reads settings; it never changes them.
      </PageHead>

      <div className="grid grid-2" style={{ marginBottom: 14, alignItems: "start" }}>
        <Card title="Install">
          <div className="filters" style={{ marginBottom: 10 }}>
            {PLATFORMS.map((item) => (
              <button key={item.key} type="button"
                      className={`chip${platform === item.key ? " on" : ""}`}
                      onClick={() => setPlatform(item.key)}>
                {item.label}
              </button>
            ))}
          </div>
          <pre className="snippet">{info?.install[platform] ?? ""}</pre>
          <div className="btn-row" style={{ marginTop: 10 }}>
            <CopyButton text={info?.install[platform] ?? ""} label="Copy command" />
            <span className="card-note">
              Run it elevated. {platform === "windows"
                ? "It installs a daily scheduled task running as SYSTEM."
                : "It installs a daily cron entry or launch daemon."}
            </span>
          </div>
        </Card>

        <Card title="Enrollment key">
          <p style={{ color: "var(--ink-secondary)", marginTop: 0 }}>
            This key lets an agent report into this system. It is not an administrative credential
            and cannot read anything back out of Bulwark.
          </p>
          <div className="btn-row">
            <code className="inline" style={{ fontSize: 13, padding: "5px 9px" }}>
              {revealed ? info?.enrollment_key : masked}
            </code>
            <button type="button" className="btn btn-sm" onClick={() => setRevealed((value) => !value)}>
              {revealed ? "Hide" : "Reveal"}
            </button>
            <CopyButton text={info?.enrollment_key ?? ""} label="Copy key" />
            <button type="button" className="btn btn-sm btn-danger" onClick={() => setConfirmRotate(true)}>
              Rotate
            </button>
          </div>

          <h3 style={{ marginTop: 20, marginBottom: 6 }}>Machine with no network route</h3>
          <p style={{ color: "var(--ink-secondary)" }}>
            Run the agent with <code className="inline">--output report.json</code>, carry the file
            over, and upload it here.
          </p>
          <input
            type="file"
            accept="application/json,.json"
            aria-label="Upload an offline agent report"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              const data = new FormData();
              data.set("file", file);
              upload.mutate(data, {
                onSuccess: (response) => notify(response.message),
                onError: (error) => notify(
                  error instanceof Error ? error.message : "Upload failed", "error"),
              });
              event.target.value = "";
            }}
          />
        </Card>
      </div>

      <div style={{ marginBottom: 14 }}>
        <Card title="Reporting endpoints" note={`${agents.length} machine(s)`} bodyClass="table-wrap">
          {agents.length === 0 ? (
            <EmptyState>
              No agent has reported yet. Install one with the command above and it appears here.
            </EmptyState>
          ) : (
            <table className="data">
              <thead>
                <tr>
                  <th>Machine</th><th>Platform</th><th>Agent</th><th>Last report</th>
                  <th className="num">Pass</th><th className="num">Fail</th><th className="num">Error</th>
                </tr>
              </thead>
              <tbody>
                {agents.map((agent) => (
                  <tr key={agent.asset_id}>
                    <td>
                      <strong>{agent.asset_name}</strong>
                      <div style={{ fontSize: 11, color: "var(--ink-muted)" }}>
                        {agent.category.replace(/_/g, " ")}
                      </div>
                    </td>
                    <td style={{ fontSize: 12 }}>{agent.platform ?? "—"}</td>
                    <td className="mono" style={{ fontSize: 12 }}>{agent.agent_version ?? "—"}</td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {formatDateTime(agent.last_seen)}
                      {agent.stale ? (
                        <span className="badge warning" style={{ marginLeft: 6 }}>
                          <span aria-hidden="true">!</span>Stale
                        </span>
                      ) : null}
                    </td>
                    <td className="num mono" style={{ color: "var(--status-good)" }}>{agent.pass_count}</td>
                    <td className="num mono"
                        style={{ color: agent.fail_count ? "var(--status-critical)" : undefined }}>
                      {agent.fail_count}
                    </td>
                    <td className="num mono">{agent.error_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <Card title="What is failing" note={`${failing.length} finding(s)`} bodyClass="table-wrap">
        {failing.length === 0 ? (
          <EmptyState>
            Nothing is failing on any in-scope asset. That is the whole point.
          </EmptyState>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Requirement</th><th className="num">Pts</th><th>Check</th>
                <th>Machines</th><th>Expected</th><th>Plan of action</th>
              </tr>
            </thead>
            <tbody>
              {failing.map((finding) => (
                <tr key={`${finding.control_id}-${finding.check_id}`}>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <Link to={`/controls/${finding.control_id}`}>
                      {finding.cmmc_id ?? finding.control_id}
                    </Link>
                    <div style={{ fontSize: 11, color: "var(--ink-muted)" }}>{finding.control_name}</div>
                  </td>
                  <td className="num"><WeightPill weight={finding.weight} /></td>
                  <td>
                    {finding.check_title}
                    <div className="mono" style={{ fontSize: 11, color: "var(--ink-muted)" }}>
                      {finding.check_id}
                    </div>
                  </td>
                  <td style={{ fontSize: 12 }}>
                    {finding.assets.slice(0, 3).map((asset) => (
                      <div key={asset.asset_id}>
                        <strong>{asset.asset_name}</strong>
                        {asset.observed ? (
                          <div style={{ color: "var(--ink-muted)" }}>{asset.observed}</div>
                        ) : null}
                      </div>
                    ))}
                    {finding.asset_count > 3 ? (
                      <div style={{ color: "var(--ink-muted)" }}>
                        and {finding.asset_count - 3} more
                      </div>
                    ) : null}
                  </td>
                  <td style={{ fontSize: 12, color: "var(--ink-secondary)" }}>
                    {finding.expected ?? "—"}
                    {finding.remediation ? (
                      <div style={{ color: "var(--ink-muted)", marginTop: 4 }}>
                        {finding.remediation}
                      </div>
                    ) : null}
                  </td>
                  <td>
                    {finding.poam_item_id ? (
                      <Link to={`/poam/${finding.poam_item_id}`}>POA&amp;M-{finding.poam_item_id}</Link>
                    ) : (
                      <Link to={`/poam/new?control=${finding.control_id}`}>Open one</Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Confirm
        open={confirmRotate}
        title="Rotate the enrollment key?"
        body="Every installed agent stops reporting until it is reconfigured with the new key. Do this if the current key has been exposed."
        confirmLabel="Rotate key"
        danger
        onCancel={() => setConfirmRotate(false)}
        onConfirm={() => {
          setConfirmRotate(false);
          rotate.mutate(undefined, {
            onSuccess: () => notify("New key issued. Reconfigure your agents."),
          });
        }}
      />
    </>
  );
}
