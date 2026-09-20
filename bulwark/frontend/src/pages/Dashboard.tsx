import { Link, useNavigate } from "react-router-dom";
import { useReadiness, useScore, useScoreHistory, useTakeSnapshot } from "../api/hooks";
import { useSystem } from "../system";
import { CoverageMeter, FamilyBars, ScoreHero, ScoreTrend, StatusBreakdown } from "../components/charts";
import {
  Card, EmptyState, ErrorState, PageHead, Spinner, StatusBadge, WeightPill, formatDateTime,
} from "../components/ui";
import { useToast } from "../components/Toast";
import type { ImplementationStatus } from "../api/types";

export default function Dashboard() {
  const { systemId } = useSystem();
  const score = useScore(systemId);
  const readiness = useReadiness(systemId);
  const history = useScoreHistory(systemId);
  const snapshot = useTakeSnapshot(systemId ?? 0);
  const navigate = useNavigate();
  const { notify } = useToast();

  if (score.isLoading || readiness.isLoading) return <Spinner />;
  if (score.isError) return <ErrorState error={score.error} />;
  if (!score.data || !readiness.data) return <EmptyState>No system selected.</EmptyState>;

  const result = score.data;
  const ready = readiness.data;

  return (
    <>
      <PageHead
        title="Readiness"
        actions={
          <button
            type="button"
            className="btn"
            disabled={snapshot.isPending}
            onClick={() => snapshot.mutate(undefined, {
              onSuccess: (created) => notify(`Snapshot saved at SPRS ${created.sprs_score}.`),
            })}
          >
            Take snapshot
          </button>
        }
      >
        Where you stand against the 110 requirements of NIST SP 800-171 Rev 2, scored the way the
        Department of Defense scores them.
      </PageHead>

      {result.assessment_blocked ? (
        <div className="callout bad" style={{ marginBottom: 14 }}>
          <strong>An assessment cannot be completed.</strong> Requirement 3.12.4 asks for a system
          security plan. Bulwark generates one for you: fill in the boundary and narratives, then
          mark 3.12.4 implemented.
        </div>
      ) : null}

      <div className="grid grid-2" style={{ marginBottom: 14 }}>
        <Card title="SPRS score" note={`${result.met_count} of ${result.total} met`}>
          <ScoreHero score={result} />
          <div style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
            <span className={`badge ${result.conditional_eligible ? "good" : "critical"}`}>
              <span aria-hidden="true">{result.conditional_eligible ? "✓" : "✗"}</span>
              Conditional certification {result.conditional_eligible ? "eligible" : "not yet"}
            </span>
            <span className={`badge ${result.final_ready ? "good" : "neutral"}`}>
              <span aria-hidden="true">{result.final_ready ? "✓" : "–"}</span>
              Final certification {result.final_ready ? "ready" : "not yet"}
            </span>
          </div>
          {result.conditional_blockers.length ? (
            <ul style={{ margin: "12px 0 0", paddingLeft: 18, color: "var(--ink-secondary)", fontSize: 13 }}>
              {result.conditional_blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
            </ul>
          ) : null}
        </Card>

        <Card title="How the 110 requirements stand">
          <StatusBreakdown
            byStatus={result.by_status}
            onSelect={(status: ImplementationStatus) => navigate(`/controls?status=${status}`)}
          />
          <div style={{ marginTop: 20 }}>
            <CoverageMeter
              label="Evidence coverage"
              covered={ready.evidence_coverage.covered}
              total={ready.evidence_coverage.total}
              pct={ready.evidence_coverage.pct}
              hint="Assessment objectives with at least one piece of evidence that has not expired."
            />
            <CoverageMeter
              label="Automated coverage"
              covered={ready.automated_coverage.covered}
              total={ready.automated_coverage.total}
              pct={ready.automated_coverage.pct}
              hint="Requirements an agent can prove, currently passing on at least one in-scope asset."
            />
          </div>
        </Card>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 14 }}>
        <Card><div className="tile">
          <div className="tile-label">Open plan of action items</div>
          <div className="tile-value">{ready.open_poam_count}</div>
          <div className="tile-sub">
            {ready.overdue_poam_count} overdue &middot; {ready.aging_poam_count} over 180 days
          </div>
        </div></Card>
        <Card><div className={`tile${ready.findings_count ? " alert" : ""}`}>
          <div className="tile-label">Failing automated checks</div>
          <div className="tile-value">{ready.findings_count}</div>
          <div className="tile-sub"><Link to="/agents">See what is failing</Link></div>
        </div></Card>
        <Card><div className="tile">
          <div className="tile-label">Endpoints reporting</div>
          <div className="tile-value">{ready.agents_reporting}</div>
          <div className="tile-sub">
            {ready.agents_stale} stale &middot; {ready.assets_total} assets in scope
          </div>
        </div></Card>
        <Card><div className={`tile${ready.stale_evidence_count ? " alert" : ""}`}>
          <div className="tile-label">Expired evidence</div>
          <div className="tile-value">{ready.stale_evidence_count}</div>
          <div className="tile-sub">
            {ready.assets_needing_review} asset{ready.assets_needing_review === 1 ? "" : "s"} need review
          </div>
        </div></Card>
      </div>

      {ready.contradiction_count > 0 ? (
        <div style={{ marginBottom: 14 }}>
          <Card
            title="Recorded as met, but the endpoints say otherwise"
            note={`${ready.contradiction_count} requirement${ready.contradiction_count === 1 ? "" : "s"}`}
          >
            <p style={{ color: "var(--ink-secondary)", marginTop: 0 }}>
              An assessor tests the objective, not the claim. These requirements are recorded as met
              while a live check on an in-scope asset is failing.
            </p>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Requirement</th><th>Practice</th><th className="num">Points at risk</th>
                    <th>Recorded as</th><th>Failing checks</th>
                  </tr>
                </thead>
                <tbody>
                  {ready.contradictions.slice(0, 8).map((item) => (
                    <tr key={item.control_id} className="clickable"
                        onClick={() => navigate(`/controls/${item.control_id}`)}>
                      <td><Link to={`/controls/${item.control_id}`}>{item.cmmc_id ?? item.control_id}</Link></td>
                      <td>{item.name}</td>
                      <td className="num"><WeightPill weight={item.weight} /></td>
                      <td><StatusBadge status={item.recorded_status as ImplementationStatus} /></td>
                      <td style={{ color: "var(--ink-secondary)", fontSize: 12 }}>
                        {item.failing_checks.join(", ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      ) : null}

      <div className="grid grid-2" style={{ marginBottom: 14 }}>
        <Card title="Progress by family" note="Requirements met">
          <FamilyBars
            families={result.families}
            onSelect={(familyId) => navigate(`/controls?family=${familyId}`)}
          />
        </Card>

        <Card title="Do these next" note="Highest score gain first">
          {ready.next_actions.length === 0 ? (
            <EmptyState>Every requirement is met. Generate your SSP and submit your score.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Requirement</th><th>Practice</th>
                    <th className="num">Points</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {ready.next_actions.map((action) => (
                    <tr key={action.control_id} className="clickable"
                        onClick={() => navigate(`/controls/${action.control_id}`)}>
                      <td><Link to={`/controls/${action.control_id}`}>
                        {action.cmmc_id ?? action.control_id}
                      </Link></td>
                      <td>
                        {action.name}
                        {action.objectives_outstanding ? (
                          <div style={{ fontSize: 11, color: "var(--ink-muted)" }}>
                            {action.objectives_outstanding} objective
                            {action.objectives_outstanding === 1 ? "" : "s"} outstanding
                          </div>
                        ) : null}
                      </td>
                      <td className="num mono" style={{ fontWeight: 600 }}>
                        +{action.points_recoverable}
                      </td>
                      <td><StatusBadge status={action.status as ImplementationStatus} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <div className="grid grid-2">
        <Card title="SPRS score over time" note={history.data?.length ? `${history.data.length} snapshots` : undefined}>
          <ScoreTrend snapshots={history.data ?? []} />
        </Card>

        <Card title="Attention">
          {ready.inheritance_gaps.length === 0 && ready.stale_evidence_count === 0
            && ready.assets_needing_review === 0 && result.warnings.length === 0 ? (
            ready.findings_count ? (
              <div className="callout warn">
                <strong>{ready.findings_count} automated check
                  {ready.findings_count === 1 ? " is" : "s are"} failing.</strong>{" "}
                Your records are internally consistent, but the endpoints disagree with them.{" "}
                <Link to="/agents">See what is failing</Link>.
              </div>
            ) : (
              <EmptyState>Nothing needs attention right now.</EmptyState>
            )
          ) : (
            <div style={{ display: "grid", gap: 10 }}>
              {result.warnings.length ? (
                <div className="callout warn">
                  <strong>{result.warnings.length} consistency warning
                    {result.warnings.length === 1 ? "" : "s"}.</strong>{" "}
                  A requirement is recorded as implemented while one of its assessment objectives is
                  not met.
                  <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                    {result.warnings.slice(0, 4).map((warning) => (
                      <li key={warning.control_id}>
                        <Link to={`/controls/${warning.control_id}`}>{warning.control_id}</Link>
                        {": "}{warning.messages[0]}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {ready.inheritance_gaps.length ? (
                <div className="callout warn">
                  <strong>Shared responsibility gaps.</strong>
                  <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                    {ready.inheritance_gaps.slice(0, 5).map((gap) => <li key={gap}>{gap}</li>)}
                  </ul>
                </div>
              ) : null}

              {ready.assets_needing_review ? (
                <div className="callout">
                  <strong>{ready.assets_needing_review} asset
                    {ready.assets_needing_review === 1 ? "" : "s"} created by an agent</strong> still
                  need a CMMC category and a rationale. <Link to="/assets">Review the inventory</Link>.
                </div>
              ) : null}

              {ready.stale_evidence_count ? (
                <div className="callout">
                  <strong>{ready.stale_evidence_count} piece
                    {ready.stale_evidence_count === 1 ? "" : "s"} of evidence has expired.</strong>{" "}
                  <Link to="/evidence?expired=true">Refresh it</Link> so it still counts.
                </div>
              ) : null}
            </div>
          )}
          <div className="card-note" style={{ marginTop: 12 }}>
            Generated {formatDateTime(ready.generated_at)}
          </div>
        </Card>
      </div>
    </>
  );
}
