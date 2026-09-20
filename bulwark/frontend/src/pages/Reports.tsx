import { useCatalog, useScore, useScoreHistory, useTakeSnapshot } from "../api/hooks";
import { useSystem } from "../system";
import { api } from "../api/client";
import { ScoreTrend } from "../components/charts";
import { Card, EmptyState, PageHead, Spinner, formatDateTime } from "../components/ui";
import { useToast } from "../components/Toast";

function DownloadRow({ label, href, hint }: { label: string; href: string; hint?: string }) {
  return (
    <a className="btn btn-sm" href={href} style={{ marginRight: 8, marginBottom: 8 }} title={hint}>
      {label}
    </a>
  );
}

export default function Reports() {
  const { systemId } = useSystem();
  const score = useScore(systemId);
  const history = useScoreHistory(systemId);
  const snapshot = useTakeSnapshot(systemId ?? 0);
  const catalog = useCatalog();
  const { notify } = useToast();

  if (!systemId) return <EmptyState>No system selected.</EmptyState>;
  if (score.isLoading) return <Spinner />;

  const base = `/systems/${systemId}`;
  const meta = (catalog.data?.meta ?? {}) as Record<string, string>;

  return (
    <>
      <PageHead title="Documents">
        Everything an assessor asks for, generated from what you have recorded. Regenerate them any
        time: they always reflect the current state, not a stale copy.
      </PageHead>

      <div className="grid grid-3" style={{ marginBottom: 14, alignItems: "start" }}>
        <Card title="System security plan">
          <p style={{ color: "var(--ink-secondary)", marginTop: 0 }}>
            All 110 requirements with your narrative, the assessment objectives, your evidence and
            your plan of action. Requirement 3.12.4 asks for exactly this document.
          </p>
          <div>
            <DownloadRow label="Word (.docx)" href={api.url(`${base}/ssp?format=docx`)} />
            <DownloadRow label="Markdown" href={api.url(`${base}/ssp?format=md`)} />
            <DownloadRow label="HTML" href={api.url(`${base}/ssp?format=html`)}
                         hint="Open and print to PDF" />
            <DownloadRow label="JSON" href={api.url(`${base}/ssp?format=json`)}
                         hint="The full context, for your own tooling" />
          </div>
        </Card>

        <Card title="Plan of action and milestones">
          <p style={{ color: "var(--ink-secondary)", marginTop: 0 }}>
            The POA&amp;M register in the columns assessors expect, including the point value of
            each outstanding requirement.
          </p>
          <div>
            <DownloadRow label="CSV" href={api.url(`${base}/poam/export?format=csv`)} />
            <DownloadRow label="Word (.docx)" href={api.url(`${base}/poam/export?format=docx`)} />
            <DownloadRow label="Markdown" href={api.url(`${base}/poam/export?format=md`)} />
          </div>
        </Card>

        <Card title="Readiness briefing">
          <p style={{ color: "var(--ink-secondary)", marginTop: 0 }}>
            A short summary for the owner: the score, what blocks certification, progress by family
            and what to do next.
          </p>
          <div>
            <DownloadRow label="Word (.docx)" href={api.url(`${base}/readiness-report?format=docx`)} />
            <DownloadRow label="Markdown" href={api.url(`${base}/readiness-report?format=md`)} />
            <DownloadRow label="HTML" href={api.url(`${base}/readiness-report?format=html`)} />
          </div>
        </Card>
      </div>

      <div className="grid grid-2">
        <Card
          title="Score history"
          actions={
            <button type="button" className="btn btn-sm" disabled={snapshot.isPending}
                    onClick={() => snapshot.mutate(undefined, {
                      onSuccess: (created) => notify(`Snapshot saved at SPRS ${created.sprs_score}.`),
                    })}>
              Take snapshot
            </button>
          }
        >
          <ScoreTrend snapshots={history.data ?? []} />
          {(history.data ?? []).length ? (
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table className="data">
                <thead>
                  <tr><th>Taken</th><th className="num">SPRS</th><th className="num">Met</th>
                    <th className="num">Readiness</th><th>Conditional</th></tr>
                </thead>
                <tbody>
                  {[...(history.data ?? [])].reverse().map((item) => (
                    <tr key={item.id}>
                      <td>{formatDateTime(item.taken_at)}</td>
                      <td className="num mono">{item.sprs_score}</td>
                      <td className="num mono">{item.met_count}/{item.total_count}</td>
                      <td className="num mono">{item.readiness_pct}%</td>
                      <td>
                        <span className={`badge ${item.conditional_eligible ? "good" : "neutral"}`}>
                          <span aria-hidden="true">{item.conditional_eligible ? "✓" : "–"}</span>
                          {item.conditional_eligible ? "Eligible" : "Not yet"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </Card>

        <Card title="What these documents are built from">
          <dl className="kv">
            <dt>Framework</dt><dd>{meta.framework ?? "NIST SP 800-171 Rev 2"}</dd>
            <dt>Assessment</dt><dd>{meta.assessment_procedures ?? "NIST SP 800-171A"}</dd>
            <dt>Scoring</dt><dd>{meta.scoring ?? "DoD Assessment Methodology"}</dd>
            <dt>Requirements</dt><dd>{catalog.data?.controls.length ?? 110} across {catalog.data?.families.length ?? 14} families</dd>
            <dt>Current score</dt>
            <dd>{score.data ? `${score.data.sprs_score} of ${score.data.max_score}` : "—"}</dd>
          </dl>
          <p className="card-note" style={{ marginTop: 14 }}>{meta.attribution ?? ""}</p>
          <div className="callout" style={{ marginTop: 12 }}>
            These documents support an assessment. They do not replace one: a CMMC Level 2
            certification requires an assessment by a certified third-party organization, and a
            self-assessment score submitted to SPRS is an assertion you are accountable for.
          </div>
        </Card>
      </div>
    </>
  );
}
