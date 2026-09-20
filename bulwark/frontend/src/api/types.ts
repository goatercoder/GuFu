/** Mirrors the backend response models (see bulwark/ARCHITECTURE.md §2 and §4). */

export type ImplementationStatus =
  | "not_implemented" | "planned" | "partially_implemented" | "implemented" | "not_applicable";
export type Responsibility = "customer" | "provider" | "shared" | "inherited";
export type PartialCredit = "none" | "mfa_partial" | "encryption_non_fips";
export type ObjectiveStatus = "met" | "not_met" | "not_applicable" | "unknown";
export type PoamStatus = "open" | "in_progress" | "completed" | "risk_accepted" | "closed";
export type PoamSource = "self_assessment" | "agent" | "c3pao" | "dibcac" | "audit" | "other";
export type RiskLevel = "low" | "moderate" | "high" | "critical";
export type EvidenceKind =
  | "document" | "policy" | "procedure" | "screenshot" | "config_export" | "log"
  | "agent_check" | "attestation" | "other";
export type EvidenceSource = "manual" | "agent";
export type AssetCategory =
  | "cui" | "security_protection" | "contractor_risk_managed" | "specialized" | "out_of_scope";
export type AssetType =
  | "workstation" | "server" | "network_device" | "mobile" | "printer" | "iot_ot"
  | "cloud_service" | "application" | "removable_media" | "facility" | "other";
export type ResponsibilityModel = "provider" | "customer" | "shared" | "not_covered";
export type ProviderKind = "csp" | "msp" | "mssp" | "other";
export type FedrampStatus =
  | "none" | "li_saas" | "low" | "moderate" | "high" | "equivalent" | "il4" | "il5";
export type Environment = "on_prem" | "cloud" | "hybrid";
export type SystemStatus = "draft" | "active" | "retired";

export interface Health { status: string; version: string }
export interface AuthMe { authenticated: boolean; setup_complete: boolean }
export interface Ok { ok: boolean }

export interface CatalogObjective { id: string; letter: string | null; text: string }

export interface CatalogControlSummary {
  id: string;
  cmmc_id: string | null;
  cmmc_level?: number;
  family_id: string;
  family_abbr: string | null;
  family_name: string | null;
  name: string;
  requirement_type: string | null;
  statement: string;
  weight: number;
  partial_credit: { deduction: number; condition: string } | null;
  poam_allowed: boolean;
  poam_never_allowed: boolean;
  nist_800_53?: string[];
  check_ids: string[];
  objective_count: number;
  guidance_summary: string;
}

export interface CatalogControlFull extends CatalogControlSummary {
  discussion: string;
  objectives: CatalogObjective[];
  assessment: { examine?: string; interview?: string; test?: string };
  guidance: {
    summary?: string;
    machine_shop_example?: string;
    typical_evidence?: string[];
    common_gaps?: string[];
    remediation_steps?: string[];
  };
}

export interface CatalogFamily {
  id: string; abbr: string | null; name: string | null;
  control_ids: string[]; control_count: number;
}

export interface CatalogCheckSummary {
  id: string; title: string; kind: string | null; platforms: string[];
  control_ids: string[]; objective_ids: string[];
}
export interface CatalogCheck extends CatalogCheckSummary {
  expected: string | null; description: string | null;
  remediation: string | null; params: Record<string, unknown>;
}

export interface CatalogResponse {
  meta: Record<string, unknown>;
  families: CatalogFamily[];
  controls: CatalogControlSummary[];
  checks: CatalogCheckSummary[];
}

export interface CrmTemplateSummary {
  id: string; name: string; provider_kind: string; description: string;
}

export interface Organization {
  id: number; name: string;
  legal_name: string | null; cage_code: string | null; uei: string | null;
  address: string | null; city: string | null; state: string | null; zip: string | null;
  website: string | null;
  primary_contact_name: string | null; primary_contact_email: string | null;
  primary_contact_phone: string | null;
  it_contact_name: string | null; it_contact_email: string | null; it_contact_phone: string | null;
  industry: string | null; employee_count: number | null; notes: string | null;
  created_at: string; updated_at: string;
}

export interface SystemRecord {
  id: number; organization_id: number; name: string;
  description: string | null; environment: Environment;
  boundary_description: string | null; cui_types: string | null;
  cui_description: string | null; data_flow_description: string | null;
  status: SystemStatus; created_at: string; updated_at: string;
  score_summary: { met_count: number; total: number };
  asset_count: number;
}

export interface Asset {
  id: number; system_id: number; name: string;
  asset_type: AssetType; category: AssetCategory; category_rationale: string | null;
  os_family: string | null; os_name: string | null; os_version: string | null;
  ip_address: string | null; mac_address: string | null;
  location: string | null; owner: string | null; description: string | null;
  serial_number: string | null; needs_review: boolean;
  agent_platform: string | null; agent_version: string | null;
  agent_last_seen: string | null; agent_last_report_id: number | null;
  created_at: string; updated_at: string;
}

export interface Provider {
  id: number; organization_id: number; name: string; kind: ProviderKind;
  service_description: string | null; fedramp_status: FedrampStatus;
  crm_reference: string | null; contact: string | null; notes: string | null;
  created_at: string; updated_at: string;
}

export interface ResponsibilityRow {
  id: number | null; provider_id: number; control_id: string;
  control_name: string; cmmc_id: string | null;
  family_id: string | null; family_abbr: string | null; weight: number;
  model: ResponsibilityModel;
  provider_responsibility: string | null; customer_responsibility: string | null;
  inherited: boolean; updated_at: string | null;
}

export interface ApplyTemplateResponse {
  template_id: string; template_name: string; applied: number;
  skipped_control_ids: string[]; disclaimer: string | null; rows: ResponsibilityRow[];
}

export interface Implementation {
  id: number; system_id: number; control_id: string;
  status: ImplementationStatus; responsibility: Responsibility;
  provider_id: number | null;
  implementation_narrative: string | null;
  customer_responsibility: string | null; provider_responsibility: string | null;
  na_justification: string | null; partial_credit: PartialCredit;
  assessed_at: string | null; assessed_by: string | null; notes: string | null;
  created_at: string; updated_at: string;
}

export interface ObjectiveCounts {
  met: number; not_met: number; not_applicable: number; unknown: number; total: number;
}

export interface CheckSummary {
  total: number; passing: number; failing: number; errors: number;
  info: number; not_applicable: number; assets: number; last_collected_at: string | null;
}

export interface ControlListItem {
  control: CatalogControlSummary;
  implementation: Implementation;
  objective_counts: ObjectiveCounts;
  evidence_count: number;
  check_summary: CheckSummary | null;
  open_poam_count: number;
  warnings: string[];
}

export interface ObjectiveRow {
  id: number | null; objective_id: string; letter: string | null; text: string;
  status: ObjectiveStatus; notes: string | null; updated_at: string | null;
}

export interface EvidenceLink {
  id: number; evidence_id: number; control_id: string; objective_id: string | null;
}

export interface Evidence {
  id: number; system_id: number; title: string; kind: EvidenceKind;
  description: string | null; file_name: string | null; content_type: string | null;
  size_bytes: number | null; sha256?: string | null;
  collected_at: string | null; expires_at: string | null; expired: boolean;
  source: EvidenceSource; asset_id: number | null;
  check_id: string | null; check_status: string | null;
  links: EvidenceLink[]; created_at: string; updated_at: string;
}

export interface CheckResult {
  id: number; report_id: number; asset_id: number; system_id: number;
  check_id: string; title: string | null; status: string;
  observed: string | null; expected: string | null;
  details: unknown; error: string | null; collected_at: string | null;
  control_ids: string[]; objective_ids: string[]; is_latest: boolean; created_at: string;
}

export interface AgentReportRow {
  id: number; asset_id: number; system_id: number;
  agent_version: string | null; platform: string | null; hostname: string | null;
  collected_at: string | null; received_at: string;
  check_count: number; fail_count: number; created_at: string;
}

export interface PoamMilestone {
  id: number; poam_item_id: number; description: string;
  due_date: string | null; completed_at: string | null; position: number;
  created_at: string; updated_at: string;
}

export interface PoamItem {
  id: number; system_id: number; control_id: string; title: string;
  weakness_description: string | null; source: PoamSource;
  risk_level: RiskLevel; status: PoamStatus; owner: string | null;
  identified_at: string | null; scheduled_completion: string | null;
  actual_completion: string | null; remediation_plan: string | null;
  resources_required: string | null; cost_estimate: string | null;
  check_id: string | null; asset_id: number | null; notes: string | null;
  milestones: PoamMilestone[]; created_at: string; updated_at: string;
}

export interface ControlDetail {
  control: CatalogControlFull;
  implementation: Implementation;
  provider: Provider | null;
  responsibility_row: ResponsibilityRow | null;
  objectives: ObjectiveRow[];
  objective_counts: ObjectiveCounts;
  evidence: Evidence[];
  check_results: CheckResult[];
  check_summary: CheckSummary | null;
  poam_items: PoamItem[];
  open_poam_count: number;
  warnings: string[];
}

export interface ScoreDeduction {
  control_id: string; cmmc_id: string | null; name: string;
  weight: number; deducted: number; status: string; reason: string | null;
}
export interface ScoreFamily {
  id: string; abbr: string; name: string; met: number; total: number; deducted_points: number;
}
export interface ScoreResult {
  sprs_score: number; max_score: number; min_score: number;
  met_count: number; not_met_count: number; na_count: number; total: number;
  readiness_pct: number;
  assessment_blocked: boolean; conditional_eligible: boolean;
  conditional_blockers: string[]; final_ready: boolean;
  deductions: ScoreDeduction[];
  warnings: { control_id: string; messages: string[] }[];
  families: ScoreFamily[];
  by_status: Record<string, number>;
}

export interface NextAction {
  control_id: string; cmmc_id: string | null; name: string; family_abbr: string;
  weight: number; points_recoverable: number; status: string;
  objectives_outstanding: number; poam_allowed: boolean;
  reason: string | null; guidance: string;
}

export interface Contradiction {
  control_id: string; cmmc_id: string | null; name: string;
  weight: number; recorded_status: string; failing_checks: string[];
}

export interface CoverageStat { covered: number; total: number; pct: number }

export interface Readiness {
  system_id: number;
  score: ScoreResult;
  evidence_coverage: CoverageStat;
  automated_coverage: CoverageStat;
  stale_evidence_count: number;
  overdue_poam_count: number;
  aging_poam_count: number;
  open_poam_count: number;
  findings_count: number;
  assets_needing_review: number;
  assets_total: number;
  agents_reporting: number;
  agents_stale: number;
  inheritance_gaps: string[];
  contradictions: Contradiction[];
  contradiction_count: number;
  next_actions: NextAction[];
  generated_at: string;
}

export interface ScoreSnapshot {
  id: number; system_id: number; taken_at: string; sprs_score: number;
  met_count: number; total_count: number; readiness_pct: number;
  conditional_eligible: boolean;
}

export interface EnrollmentInfo {
  system_id: number; enrollment_key: string; server_url: string;
  install: { windows: string; linux: string; macos: string };
}

export interface AgentStatusItem {
  asset_id: number; asset_name: string; hostname: string | null;
  category: AssetCategory; platform: string | null; agent_version: string | null;
  last_seen: string | null; stale: boolean;
  pass_count: number; fail_count: number; error_count: number;
  info_count: number; not_applicable_count: number;
}

export interface FindingAsset {
  asset_id: number; asset_name: string; status: string;
  observed: string | null; collected_at: string | null;
}
export interface Finding {
  control_id: string; cmmc_id: string | null; control_name: string; weight: number;
  check_id: string; check_title: string; expected: string | null; remediation: string | null;
  objective_ids: string[]; asset_count: number; assets: FindingAsset[];
  poam_item_id: number | null;
}

export interface IngestResponse {
  ok: boolean; asset_id: number; system_id: number;
  checks_ingested: number; findings: number; poam_created: number;
  unknown_checks: string[]; message: string;
}

export interface ActivityEntry {
  id: number; system_id: number | null; actor: string; action: string;
  entity_type: string; entity_id: number | null; summary: string; created_at: string;
}
