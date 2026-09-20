# Bulwark — architecture and build contract

Bulwark is CMMC Level 2 / NIST SP 800-171 Rev 2 compliance automation for small defense suppliers
(the 40-person machine shop with one IT person). One SQLite file, one Python process, one static
frontend, one dependency-free agent script per platform. Everything in this document is the
**contract** that the backend, agents and frontend are built against. When code and this document
disagree, fix the code.

## 1. Layout

```
bulwark/
  ARCHITECTURE.md            this file
  README.md                  user-facing: what it is, quickstart, deployment
  Makefile                   make setup / dev / test / build / lint / catalog
  catalog/
    sources/                 NIST SP 800-171 Rev 2 + 800-171A OSCAL catalog (see ATTRIBUTION.md)
    enrichment/              hand-curated JSON merged into the catalog by build_catalog.py
      families.json          family id -> {abbr, name}
      scoring_weights.json   DoD Assessment Methodology point values, partial credit, POA&M rules
      cmmc_names.json        control id -> CMMC practice name ("Authorized Access Control")
      nist80053_map.json     control id -> [800-53 Rev 5 control ids]
      guidance.json          control id -> plain-language guidance for a small shop, examples, evidence
      crm_templates/*.json   shared-responsibility starting templates for common providers
    checks.json              the automated check catalog (check id -> controls/objectives/platforms)
    build_catalog.py         OSCAL + enrichment -> cmmc_l2_catalog.json (idempotent, deterministic)
    cmmc_l2_catalog.json     BUILT ARTIFACT, committed. The only catalog file the backend reads.
  backend/
    requirements.txt, requirements-dev.txt, pyproject.toml (ruff + pytest config)
    bulwark/                 FastAPI application package (see §4)
    tests/                   pytest
  agent/
    bulwark_agent.py         Linux / macOS / Windows collector, Python 3.8+ stdlib ONLY
    Bulwark-Agent.ps1        Windows collector, PowerShell 5.1+ (no modules beyond in-box)
    README.md                install + scheduling instructions
    tests/                   pytest for the Python agent (mocked commands)
  frontend/                  Vite + React 19 + TypeScript + Tailwind 4 + react-router + react-query
  docs/                      scoping.md, shared-responsibility.md, deployment.md, scoring.md
  Dockerfile, docker-compose.yml, start.sh, start.bat
```

Runtime data lives in `bulwark/backend/data/` (gitignored): `bulwark.db` (SQLite), `evidence/`
(uploaded files), `secret.key`, `admin_password.txt` (only if auto-generated).

## 2. Catalog contract (`catalog/cmmc_l2_catalog.json`)

```jsonc
{
  "meta": {"framework": "NIST SP 800-171 Rev 2", "cmmc_level": 2, "built": "...", "sources": [...]},
  "families": [
    {"id": "3.1", "abbr": "AC", "name": "Access Control", "control_ids": ["3.1.1", ...]}
  ],
  "controls": [
    {
      "id": "3.1.1",                       // canonical key used EVERYWHERE (DB, API, UI)
      "cmmc_id": "AC.L2-3.1.1",            // 32 CFR 170 identifier
      "family_id": "3.1", "family_abbr": "AC", "family_name": "Access Control",
      "name": "Authorized Access Control", // CMMC practice name (from cmmc_names.json)
      "requirement_type": "basic" | "derived",
      "statement": "Limit system access to ...",   // verbatim Rev 2
      "discussion": "...",                          // verbatim Rev 2
      "objectives": [ {"id": "3.1.1[a]", "letter": "a", "text": "authorized users are identified."} ],
      "assessment": {"examine": "...", "interview": "...", "test": "..."},  // 800-171A
      "weight": 5 | 3 | 1 | 0,             // 0 only for 3.12.4 (unscored)
      "partial_credit": null | {"deduction": 3, "condition": "..."},       // 3.5.3 and 3.13.11 only
      "poam_allowed": true | false,        // 170.21: weight 1 and not in never-allowed list; 3.13.11 partial special-cased in code
      "nist_800_53": ["AC-2", "AC-3", "AC-17"],
      "guidance": {"summary": "...", "machine_shop_example": "...", "typical_evidence": [...], "common_gaps": [...], "remediation_steps": [...]},
      "check_ids": ["win.firewall.enabled", ...]   // automated checks that produce evidence for this control
    }
  ],
  "checks": [ ... contents of checks.json ... ]
}
```

Objective ids use the 800-171A form `3.1.1[a]`. Control ids are plain `3.1.1`. Never invent other
forms in the DB or API.

## 3. Automated check contract (`catalog/checks.json` and the agent report)

Every check has a stable `id` (`<platform-scope>.<area>.<name>`, e.g. `os.firewall.enabled`,
`win.audit.policy`, `nix.ssh.root_login`). `os.*` checks are implemented on every platform; `win.*` only
on Windows; `nix.*` on Linux/macOS; `mac.*` macOS only. checks.json is the single source of truth
for the control/objective mapping — agents send only the check id, status and observation; the
**server** maps to controls.

Agent report (POST `/api/agents/report`, header `Authorization: Bearer <enrollment key>`,
`Content-Type: application/json`):

```jsonc
{
  "schema_version": 1,
  "agent": {"name": "bulwark-agent", "version": "0.1.0", "platform": "windows" | "linux" | "macos"},
  "asset": {
    "hostname": "SHOP-CNC-01", "fqdn": "shop-cnc-01.acme.local",
    "os_family": "windows" | "linux" | "macos", "os_name": "Windows 11 Pro", "os_version": "10.0.22631",
    "arch": "x86_64", "domain": "ACME" | null, "serial_number": "..." | null,
    "ip_addresses": ["10.0.1.15"], "mac_addresses": ["00:11:22:33:44:55"], "logged_in_users": ["acme\\joe"]
  },
  "collected_at": "2026-09-20T14:03:00Z",
  "checks": [
    {
      "check_id": "os.firewall.enabled",
      "status": "pass" | "fail" | "error" | "not_applicable" | "info",
      "observed": "Domain: On; Private: On; Public: On",     // short human string, always present
      "expected": "All firewall profiles enabled",            // short human string
      "details": { ...any JSON... },                          // optional raw data
      "error": null | "message"                               // set when status == error
    }
  ],
  "inventory": {
    "local_users": [{"name": "joe", "enabled": true, "admin": false, "last_logon": "..."|null}],
    "software": [{"name": "...", "version": "...", "publisher": "..."|null}],
    "listening_ports": [{"proto": "tcp", "port": 3389, "process": "svchost"|null}],
    "services": [{"name": "...", "state": "running"|"stopped"}]
  }
}
```

Server response: `{"ok": true, "asset_id": 12, "system_id": 1, "checks_ingested": 31,
"findings": 4, "message": "..."}`. Unknown check ids are stored with `status` as sent and no
mapping. `info` checks never fail but do produce evidence.

Offline mode: `bulwark_agent.py --output report.json` / `Bulwark-Agent.ps1 -Output report.json`
writes the same JSON for sneaker-net upload via `POST /api/systems/{id}/agent-reports/upload`.

## 4. Backend

Python 3.11, FastAPI, SQLModel (SQLAlchemy 2 + Pydantic 2), SQLite (WAL), Jinja2, python-docx,
python-multipart, uvicorn. Single-tenant: one Organization per install, many Systems (assessment
scopes) per Organization.

### 4.1 Package layout (`backend/bulwark/`)

```
main.py          create_app(): FastAPI, CORS for dev, static serving of ../frontend/dist, /api routers
config.py        Settings (pydantic-settings): BULWARK_DATA_DIR, BULWARK_ADMIN_PASSWORD, BULWARK_SECRET,
                 BULWARK_EVIDENCE_TTL_DAYS=30, BULWARK_AUTO_POAM=true, BULWARK_HOST/PORT
db.py            engine, session dependency, init_db(), migrations via SQLModel.metadata.create_all
models.py        SQLModel tables (§4.2)
schemas.py       request/response Pydantic models (§4.3 API)
catalog.py       load cmmc_l2_catalog.json once; lookups: control(id), objectives(id), checks(id), families()
auth.py          admin password login -> signed session cookie; enrollment-key auth for agents
scoring.py       pure functions (§5). NO database access; takes plain dicts/dataclasses.
evidence_rules.py  check-result -> evidence/objective mapping, findings, auto-POA&M
ssp/             generator: build_context(system) -> dict; render markdown/html/docx
reports.py       POA&M export (csv/md/docx), readiness report
seed.py          seed_demo(): "Precision Machining LLC" with realistic data (assets, providers, statuses, POA&M, agent reports)
api/             routers: auth, catalog, organization, systems, assets, providers, controls, poam,
                 evidence, agents, scoring, reports, admin
```

### 4.2 Data model (SQLModel tables)

All tables have integer `id` PK and `created_at`/`updated_at` (UTC ISO strings or datetimes).

| table | fields |
|---|---|
| organization | name, legal_name, cage_code, uei, address, city, state, zip, website, primary_contact_name/email/phone, it_contact_name/email/phone, industry ("Precision machining"), employee_count, notes |
| system | organization_id, name, description, environment (`on_prem`/`cloud`/`hybrid`), boundary_description, cui_types (text), cui_description, data_flow_description, enrollment_key (random, 32 chars), status (`draft`/`active`/`retired`) |
| asset | system_id, name, asset_type (`workstation`,`server`,`network_device`,`mobile`,`printer`,`iot_ot`,`cloud_service`,`application`,`removable_media`,`facility`,`other`), category (`cui`,`security_protection`,`contractor_risk_managed`,`specialized`,`out_of_scope`), category_rationale, os_family, os_name, os_version, ip_address, mac_address, location, owner, description, serial_number, needs_review (bool; true when auto-created by an agent), agent_platform, agent_version, agent_last_seen, agent_last_report_id |
| provider | organization_id, name, kind (`csp`,`msp`,`mssp`,`other`), service_description, fedramp_status (`none`,`li_saas`,`low`,`moderate`,`high`,`equivalent`,`il4`,`il5`), crm_reference (url/doc name), contact, notes |
| responsibility_row | provider_id, control_id, model (`provider`,`customer`,`shared`,`not_covered`), provider_responsibility, customer_responsibility, inherited (bool) |
| control_implementation | system_id, control_id, status (`not_implemented`,`planned`,`partially_implemented`,`implemented`,`not_applicable`), responsibility (`customer`,`provider`,`shared`,`inherited`), provider_id?, implementation_narrative, customer_responsibility, provider_responsibility, na_justification, partial_credit (`none`,`mfa_partial`,`encryption_non_fips`), assessed_at, assessed_by, notes. UNIQUE(system_id, control_id) |
| objective_assessment | implementation_id, objective_id ("3.1.1[a]"), status (`met`,`not_met`,`not_applicable`,`unknown`), notes. UNIQUE(implementation_id, objective_id) |
| poam_item | system_id, control_id, title, weakness_description, source (`self_assessment`,`agent`,`c3pao`,`dibcac`,`audit`,`other`), risk_level (`low`,`moderate`,`high`,`critical`), status (`open`,`in_progress`,`completed`,`risk_accepted`,`closed`), owner, identified_at, scheduled_completion, actual_completion, remediation_plan, resources_required, cost_estimate, check_id?, asset_id?, notes |
| poam_milestone | poam_item_id, description, due_date, completed_at, position |
| evidence | system_id, title, kind (`document`,`policy`,`procedure`,`screenshot`,`config_export`,`log`,`agent_check`,`attestation`,`other`), description, file_name, file_path, content_type, size_bytes, sha256, collected_at, expires_at, source (`manual`,`agent`), asset_id?, check_id?, check_status? |
| evidence_link | evidence_id, control_id, objective_id? |
| agent_report | asset_id, system_id, agent_version, platform, hostname, collected_at, received_at, raw_json, check_count, fail_count |
| check_result | report_id, asset_id, system_id, check_id, title, status, observed, expected, details_json, error, collected_at, control_ids_json, objective_ids_json, is_latest (bool: newest result for (asset, check)) |
| score_snapshot | system_id, taken_at, sprs_score, met_count, total_count, readiness_pct, conditional_eligible, details_json |
| activity_log | system_id?, actor, action, entity_type, entity_id, summary |

Rules: creating a System creates 110 `control_implementation` rows (`not_implemented`, `customer`)
and their objective_assessment rows (`unknown`). Deleting a System cascades.

### 4.3 API (all under `/api`, JSON; errors as `{"detail": "..."}`)

Auth: `POST /auth/login {password}` -> sets HttpOnly cookie `bulwark_session`; `POST /auth/logout`;
`GET /auth/me` -> `{authenticated, setup_complete}`. Everything else requires the cookie **or**
`Authorization: Bearer <admin password>` except `/health`, `/auth/*`, `/agents/report`
(enrollment key). `GET /health` -> `{status:"ok", version}`.

```
GET  /catalog                         families + controls (no discussion/assessment text) + checks summary
GET  /catalog/controls/{control_id}   full control incl. discussion, objectives, assessment, guidance
GET  /catalog/checks                  check catalog
GET  /catalog/crm-templates           [{id, name, provider_kind, description}]

GET  /organization                    404 until created
PUT  /organization                    create-or-update

GET  /systems                         list with score summary per system
POST /systems                         create (seeds implementations)
GET  /systems/{id}   PUT  DELETE

GET  /systems/{id}/assets            ?category=&type=&q=
POST /systems/{id}/assets
GET  /assets/{id}   PUT   DELETE
GET  /assets/{id}/checks             latest check results for the asset
GET  /assets/{id}/reports            report history (no raw json)

GET  /providers   POST               (org-wide)
GET  /providers/{id}  PUT  DELETE
GET  /providers/{id}/matrix          responsibility rows for all 110 controls (missing -> not_covered)
PUT  /providers/{id}/matrix          bulk upsert [{control_id, model, provider_responsibility, customer_responsibility, inherited}]
POST /providers/{id}/matrix/apply-template {template_id}

GET  /systems/{id}/controls          110 rows: catalog summary + implementation + objective counts + evidence_count + latest check summary + open_poam_count
GET  /systems/{id}/controls/{cid}    detail: catalog control + implementation + objectives (with statuses) + evidence + check results + poam items
PUT  /systems/{id}/controls/{cid}    update implementation fields (partial update)
PUT  /systems/{id}/controls/{cid}/objectives   [{objective_id, status, notes}]
POST /systems/{id}/controls/bulk     [{control_id, status?, responsibility?, provider_id?}]

GET  /systems/{id}/poam              ?status=&control_id=  (items with milestones)
POST /systems/{id}/poam
GET  /poam/{id}  PUT  DELETE
POST /poam/{id}/milestones   PUT /milestones/{id}   DELETE /milestones/{id}
POST /poam/{id}/transition   {status, note?}   validates workflow: open->in_progress->completed->closed, any->risk_accepted, closed requires completed or risk_accepted

GET  /systems/{id}/evidence          ?kind=&control_id=&source=&expired=
POST /systems/{id}/evidence          multipart: file? + fields (title, kind, description, collected_at?, expires_at?, control_ids[], objective_ids[])
GET  /evidence/{id}  PUT  DELETE
GET  /evidence/{id}/download
POST /evidence/{id}/links   {control_id, objective_id?}     DELETE /evidence/{id}/links/{link_id}

GET  /systems/{id}/enrollment        {enrollment_key, server_url, install: {windows, linux, macos}}   (commands ready to paste)
POST /systems/{id}/enrollment/rotate
POST /agents/report                  (bearer enrollment key) -> ingest (§6)
POST /systems/{id}/agent-reports/upload   (admin, multipart or JSON body) -> same ingest
GET  /systems/{id}/agent-status      per asset: last seen, agent version, pass/fail/error counts, stale (bool)
GET  /systems/{id}/findings          failing/error checks grouped by control with affected assets

GET  /systems/{id}/score             live computation (§5) -> ScoreResult
GET  /systems/{id}/score/history     snapshots
POST /systems/{id}/score/snapshot
GET  /systems/{id}/readiness         ScoreResult + family breakdown + evidence coverage + agent coverage + stale evidence + overdue POA&M + top next actions

GET  /systems/{id}/ssp?format=md|html|docx|json
GET  /systems/{id}/poam/export?format=csv|md|docx
GET  /systems/{id}/readiness-report?format=md|html|docx

POST /admin/seed-demo                creates demo org+system if none; returns ids
GET  /admin/activity                 recent activity_log
```

### 4.4 ScoreResult shape

```jsonc
{
  "sprs_score": 73, "max_score": 110, "min_score": -203,
  "met_count": 81, "not_met_count": 29, "na_count": 3, "total": 110,
  "readiness_pct": 76.4,                  // (met + na) / 110 * 100
  "assessment_blocked": false,            // true when 3.12.4 (SSP) not implemented
  "conditional_eligible": false,          // 170.21(a)(2) rules
  "conditional_blockers": ["score 73 < 88", "5-point requirements not met: 3.5.3, 3.13.11", "never-POA&M requirement not met: 3.1.22"],
  "deductions": [{"control_id": "3.5.3", "weight": 5, "deducted": 3, "status": "partially_implemented", "reason": "MFA partial credit"}],
  "families": [{"id": "3.1", "abbr": "AC", "met": 18, "total": 22, "deducted_points": 7}],
  "by_status": {"implemented": 78, "not_applicable": 3, "partially_implemented": 10, "planned": 9, "not_implemented": 10}
}
```

## 5. Scoring rules (`scoring.py`, pure)

1. A control is **met** when implementation status is `implemented` or `not_applicable`.
   `not_applicable` without a non-empty `na_justification` is a validation warning but still met
   (assessors decide; we flag it).
2. Consistency: if status is `implemented` but any objective is `not_met`, the control is treated
   as `partially_implemented` for scoring and listed under `warnings`.
3. SPRS score = 110 − Σ deductions over not-met controls, deduction = weight, except:
   * `3.5.3` with `partial_credit == "mfa_partial"` deducts 3;
   * `3.13.11` with `partial_credit == "encryption_non_fips"` deducts 3;
   * `3.12.4` deducts 0 but sets `assessment_blocked = true`.
4. Conditional CMMC certification eligibility (32 CFR 170.21(a)(2)): sprs_score ≥ 88 (i.e. ≥ 80 %),
   every not-met control has weight 1 except `3.13.11` when its deduction is 3, and none of
   3.1.20, 3.1.22, 3.10.3, 3.10.4, 3.10.5 are not-met. `assessment_blocked` also blocks.
5. Final-certification-ready = all 110 met.
6. Family breakdown, status histogram and deductions list are returned for the UI.

Extra readiness signals (`/readiness`): evidence coverage (% objectives with ≥1 non-expired
evidence link), automated coverage (% controls with ≥1 passing latest check across in-scope assets),
stale evidence count, overdue POA&M count (scheduled_completion < today and not completed/closed),
POA&M items older than 180 days, assets `needs_review`, controls with `inherited/provider`
responsibility but no provider or matrix row, and a ranked "next actions" list (highest weight
not-met first, tie-break by fewest objectives outstanding).

## 6. Agent ingestion (`evidence_rules.py`)

1. Resolve system by enrollment key; find asset by (system_id, hostname case-insensitive) else
   create with `needs_review=true`, category `cui`, type inferred from platform.
2. Store agent_report; for each check: store check_result (mark previous `is_latest=false`), map
   control/objective ids from checks.json.
3. Evidence: upsert one `evidence` row per (asset, check_id) of kind `agent_check`, source
   `agent`, `collected_at` = report time, `expires_at` = collected + `BULWARK_EVIDENCE_TTL_DAYS`,
   `check_status` = status, links = mapped controls/objectives.
4. Findings: latest `fail` results (any in-scope asset) grouped by control. If `BULWARK_AUTO_POAM`
   and no open/in_progress POA&M item exists for (system, control), create one with
   `source=agent`, title "<check title> failing on N asset(s)", risk from control weight
   (5→high, 3→moderate, 1→low), scheduled_completion = today + 30 days, one milestone.
   When all latest results for that check pass again, append a note to the POA&M item; never
   auto-close.
5. Objective assessments are **not** auto-changed by agents (assessor decides); the UI shows the
   check evidence next to the objective.

## 7. SSP generator

`ssp/build_context.py` produces one dict used by all formats:
system identification (org, CAGE, UEI, contacts, version/date), system environment and boundary,
CUI description and data flows, asset inventory grouped by CMMC category (with counts and an
explicit out-of-scope justification list), external service providers and shared-responsibility
summary, roles and responsibilities, then all 14 families × requirements with: id, CMMC id, name,
statement, status, responsibility (+provider), implementation narrative (or a generated placeholder
"NOT YET DOCUMENTED — see POA&M-xx"), objectives table, evidence references, POA&M references.
Appendices: POA&M summary, evidence index, agent coverage table, catalog/version info.
Markdown is the canonical rendering (Jinja2 template); HTML wraps it with a print stylesheet;
DOCX uses python-docx with real headings/tables so it opens cleanly in Word.

## 8. Frontend

Vite + React 19 + TypeScript strict + Tailwind 4 (`@tailwindcss/vite`) + react-router 7 +
@tanstack/react-query 5 + recharts. `src/api/client.ts` wraps fetch with `credentials: "include"`
and `src/api/types.ts` mirrors §4.3 shapes exactly. Dev proxy `/api` -> `http://127.0.0.1:8800`.
Production: `npm run build` -> `frontend/dist`, served by FastAPI at `/` with SPA fallback.

Routes: `/login`, `/setup` (wizard: org → system → scope → providers), `/` dashboard,
`/controls`, `/controls/:id`, `/poam`, `/poam/:id`, `/evidence`, `/assets`, `/providers`,
`/providers/:id`, `/agents`, `/reports`, `/settings`. Layout: left nav with system switcher, top
bar with SPRS score chip. Design: calm, dense, readable; status colours: implemented green,
partially amber, planned blue, not-implemented red, N/A gray; weights shown as 5/3/1 pills.

## 9. Quality bar

* `make test` = backend pytest + agent pytest; `make lint` = ruff; `make build` = frontend typecheck
  + vite build. All must pass before a push. CI: `.github/workflows/bulwark-ci.yml` (paths
  `bulwark/**`).
* Tests must cover: scoring (every rule in §5 with fixtures), catalog integrity (14/110/320,
  weights 44/14/51/1, every check maps to existing control+objective ids), ingestion (new asset,
  evidence upsert, auto-POA&M, is_latest flip), POA&M transitions, SSP rendering (md + docx open),
  API auth (401 without cookie, agent key rejects admin routes), evidence upload/link/download.
* No secrets in the repo. Enrollment keys and the admin password are never logged.

## 10. Catalog enrichment files (`catalog/enrichment/families/<family_id>.json`)

One file per family, merged by `build_catalog.py` (overrides the flat `cmmc_names.json` /
`nist80053_map.json` / `guidance.json`):

```jsonc
{
  "family_id": "3.1",
  "controls": {
    "3.1.1": {
      "name": "Authorized Access Control",            // CMMC L2 practice name (32 CFR 170 / CMMC Assessment Guide L2)
      "nist_800_53": ["AC-2", "AC-3", "AC-17"],        // SP 800-53 Rev 5 ids (800-171 Rev 2 Appendix D mapping)
      "weight_claimed": 5,                             // what your research says; build fails if it disagrees with scoring_weights.json
      "weight_sources": ["https://..."],
      "guidance": {
        "summary": "2-3 plain-English sentences for a non-specialist IT person.",
        "machine_shop_example": "Concrete example for a 40-person job shop.",
        "typical_evidence": ["...", "..."],
        "common_gaps": ["...", "..."],
        "remediation_steps": ["...", "..."]
      }
    }
  }
}
```

CRM starting templates live in `catalog/enrichment/crm_templates/<id>.json`:
`{"id","name","provider_kind","description","disclaimer","rows":[{"control_id","model","provider_responsibility","customer_responsibility","inherited"}]}`
with one row per control (110). `model` ∈ provider | customer | shared | not_covered.
