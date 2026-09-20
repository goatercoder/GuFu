import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useCatalog, useControls, useUpdateImplementation } from "../api/hooks";
import { useSystem } from "../system";
import {
  Card, EmptyState, ErrorState, PageHead, Spinner, STATUS_META, STATUS_ORDER, WeightPill,
} from "../components/ui";
import { useToast } from "../components/Toast";
import type { ControlListItem } from "../api/types";

type SortKey = "id" | "weight" | "status" | "objectives" | "evidence";

export default function Controls() {
  const { systemId } = useSystem();
  const controls = useControls(systemId);
  const catalog = useCatalog();
  const update = useUpdateImplementation(systemId ?? 0);
  const [params, setParams] = useSearchParams();
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "id", dir: 1 });
  const [search, setSearch] = useState("");
  const navigate = useNavigate();
  const { notify } = useToast();

  const family = params.get("family") ?? "";
  const status = params.get("status") ?? "";
  const weight = params.get("weight") ?? "";

  function setFilter(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next, { replace: true });
  }

  const rows = useMemo(() => {
    const all = controls.data ?? [];
    const term = search.trim().toLowerCase();
    const filtered = all.filter((row) => {
      if (family && row.control.family_id !== family) return false;
      if (status && row.implementation.status !== status) return false;
      if (weight && String(row.control.weight) !== weight) return false;
      if (!term) return true;
      return (
        row.control.id.includes(term)
        || (row.control.cmmc_id ?? "").toLowerCase().includes(term)
        || row.control.name.toLowerCase().includes(term)
        || row.control.statement.toLowerCase().includes(term)
      );
    });
    const compare = (a: ControlListItem, b: ControlListItem): number => {
      switch (sort.key) {
        case "weight": return a.control.weight - b.control.weight;
        case "status":
          return STATUS_ORDER.indexOf(a.implementation.status)
            - STATUS_ORDER.indexOf(b.implementation.status);
        case "objectives":
          return (a.objective_counts.met / (a.objective_counts.total || 1))
            - (b.objective_counts.met / (b.objective_counts.total || 1));
        case "evidence": return a.evidence_count - b.evidence_count;
        default: {
          const left = a.control.id.split(".").map(Number);
          const right = b.control.id.split(".").map(Number);
          for (let index = 0; index < 3; index += 1) {
            const diff = (left[index] ?? 0) - (right[index] ?? 0);
            if (diff) return diff;
          }
          return 0;
        }
      }
    };
    return [...filtered].sort((a, b) => compare(a, b) * sort.dir);
  }, [controls.data, family, status, weight, search, sort]);

  if (controls.isLoading) return <Spinner />;
  if (controls.isError) return <ErrorState error={controls.error} />;

  const families = catalog.data?.families ?? [];
  const met = rows.filter((row) =>
    row.implementation.status === "implemented" || row.implementation.status === "not_applicable").length;

  function header(key: SortKey, label: string, numeric = false) {
    return (
      <th
        className={`sortable${numeric ? " num" : ""}`}
        onClick={() => setSort((current) =>
          current.key === key ? { key, dir: current.dir === 1 ? -1 : 1 } : { key, dir: 1 })}
      >
        {label}{sort.key === key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
      </th>
    );
  }

  return (
    <>
      <PageHead title="Security requirements">
        All 110 requirements of NIST SP 800-171 Rev 2. Set a status here, or open one to record the
        narrative, assess its objectives and attach evidence.
      </PageHead>

      <div className="filters">
        <input
          className="compact"
          style={{ minWidth: 230 }}
          type="text"
          placeholder="Search id, name or requirement text"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          aria-label="Search requirements"
        />
        <select className="compact" value={family} aria-label="Filter by family"
                onChange={(event) => setFilter("family", event.target.value)}>
          <option value="">All families</option>
          {families.map((item) => (
            <option key={item.id} value={item.id}>
              {item.abbr} — {item.name} ({item.control_count})
            </option>
          ))}
        </select>
        <select className="compact" value={status} aria-label="Filter by status"
                onChange={(event) => setFilter("status", event.target.value)}>
          <option value="">Any status</option>
          {STATUS_ORDER.map((value) => (
            <option key={value} value={value}>{STATUS_META[value].label}</option>
          ))}
        </select>
        {["5", "3", "1"].map((value) => (
          <button key={value} type="button" className={`chip${weight === value ? " on" : ""}`}
                  onClick={() => setFilter("weight", weight === value ? "" : value)}>
            {value}-point
          </button>
        ))}
        {(family || status || weight || search) ? (
          <button type="button" className="btn-link"
                  onClick={() => { setParams(new URLSearchParams(), { replace: true }); setSearch(""); }}>
            Clear filters
          </button>
        ) : null}
        <span style={{ marginLeft: "auto", color: "var(--ink-secondary)", fontSize: 12 }}>
          {rows.length} shown &middot; {met} met
        </span>
      </div>

      <Card bodyClass="table-wrap">
        {rows.length === 0 ? (
          <EmptyState>No requirements match these filters.</EmptyState>
        ) : (
          <table className="data">
            <thead>
              <tr>
                {header("id", "Practice")}
                <th>Name</th>
                {header("weight", "Pts", true)}
                {header("status", "Status")}
                <th>Responsibility</th>
                {header("objectives", "Objectives", true)}
                {header("evidence", "Evidence", true)}
                <th className="num">Checks</th>
                <th className="num">POA&amp;M</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const counts = row.objective_counts;
                const checks = row.check_summary;
                return (
                  <tr key={row.control.id}>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <Link to={`/controls/${row.control.id}`}>
                        {row.control.cmmc_id ?? row.control.id}
                      </Link>
                      {row.warnings.length ? (
                        <span title={row.warnings.join("; ")}
                              style={{ color: "var(--status-warning)", marginLeft: 5 }}>!</span>
                      ) : null}
                    </td>
                    <td>
                      <Link to={`/controls/${row.control.id}`} style={{ color: "inherit" }}>
                        {row.control.name}
                      </Link>
                    </td>
                    <td className="num"><WeightPill weight={row.control.weight} /></td>
                    <td>
                      <select
                        className="compact"
                        value={row.implementation.status}
                        aria-label={`Status for ${row.control.id}`}
                        onChange={(event) => update.mutate(
                          { controlId: row.control.id, body: { status: event.target.value } },
                          {
                            onError: (error) => notify(
                              error instanceof Error ? error.message : "Could not save", "error"),
                          },
                        )}
                      >
                        {STATUS_ORDER.map((value) => (
                          <option key={value} value={value}>{STATUS_META[value].label}</option>
                        ))}
                      </select>
                    </td>
                    <td style={{ color: "var(--ink-secondary)", fontSize: 12 }}>
                      {row.implementation.responsibility.replace("_", " ")}
                    </td>
                    <td className="num mono">
                      {counts.met + counts.not_applicable}/{counts.total}
                    </td>
                    <td className="num mono">{row.evidence_count || "—"}</td>
                    <td className="num">
                      {checks && checks.total ? (
                        <span className={`badge ${checks.failing ? "critical" : "good"}`}>
                          <span aria-hidden="true">{checks.failing ? "✗" : "✓"}</span>
                          {checks.failing ? `${checks.failing} failing` : `${checks.passing} pass`}
                        </span>
                      ) : <span style={{ color: "var(--ink-muted)" }}>—</span>}
                    </td>
                    <td className="num">
                      {row.open_poam_count ? (
                        <button type="button" className="btn-link"
                                onClick={() => navigate(`/poam?control=${row.control.id}`)}>
                          {row.open_poam_count}
                        </button>
                      ) : <span style={{ color: "var(--ink-muted)" }}>—</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
