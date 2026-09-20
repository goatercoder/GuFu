"""Pydantic request/response models for the API (ARCHITECTURE.md §4.3).

Datetimes are timezone-aware UTC and serialise as ISO 8601 (``2026-09-20T14:03:00Z``);
dates serialise as ``YYYY-MM-DD``. Enum fields serialise as their plain string values.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import (
    AssetCategory,
    AssetType,
    CheckStatus,
    Environment,
    EvidenceKind,
    EvidenceSource,
    FedrampStatus,
    ImplementationStatus,
    ObjectiveStatus,
    PartialCredit,
    PoamSource,
    PoamStatus,
    ProviderKind,
    Responsibility,
    ResponsibilityModel,
    RiskLevel,
    SystemStatus,
)


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ApiModel(BaseModel):
    """Base for all API models: enum values, ORM attribute access, strip whitespace."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True, str_strip_whitespace=True)


# --------------------------------------------------------------------------------------------
# Generic
# --------------------------------------------------------------------------------------------
class OkResponse(ApiModel):
    ok: bool = True


class HealthResponse(ApiModel):
    status: str = "ok"
    version: str


# --------------------------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------------------------
class LoginRequest(ApiModel):
    password: str = Field(min_length=1)


class AuthMeResponse(ApiModel):
    authenticated: bool
    setup_complete: bool


# --------------------------------------------------------------------------------------------
# Catalog
# --------------------------------------------------------------------------------------------
class CatalogFamily(ApiModel):
    id: str
    abbr: str | None = None
    name: str | None = None
    control_ids: list[str] = []
    control_count: int = 0


class CatalogObjective(ApiModel):
    id: str
    letter: str | None = None
    text: str = ""


class CatalogControlSummary(ApiModel):
    """A control without the long-form discussion/assessment/guidance text."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True, extra="allow")

    id: str
    cmmc_id: str | None = None
    family_id: str
    family_abbr: str | None = None
    family_name: str | None = None
    name: str = ""
    requirement_type: str | None = None
    statement: str = ""
    weight: int = 0
    partial_credit: dict[str, Any] | None = None
    poam_allowed: bool = False
    poam_never_allowed: bool = False
    nist_800_53: list[str] = []
    check_ids: list[str] = []
    objective_count: int = 0
    guidance_summary: str = ""


class CatalogControlFull(CatalogControlSummary):
    discussion: str = ""
    objectives: list[CatalogObjective] = []
    assessment: dict[str, Any] = {}
    guidance: dict[str, Any] = {}


class CatalogCheckSummary(ApiModel):
    id: str
    title: str
    kind: str | None = None
    platforms: list[str] = []
    control_ids: list[str] = []
    objective_ids: list[str] = []


class CatalogCheck(CatalogCheckSummary):
    model_config = ConfigDict(from_attributes=True, extra="allow")

    expected: str | None = None
    description: str | None = None
    remediation: str | None = None
    params: dict[str, Any] = {}


class CatalogResponse(ApiModel):
    meta: dict[str, Any]
    families: list[CatalogFamily]
    controls: list[CatalogControlSummary]
    checks: list[CatalogCheckSummary]


class CrmTemplateSummary(ApiModel):
    id: str
    name: str
    provider_kind: str
    description: str = ""


# --------------------------------------------------------------------------------------------
# Organization
# --------------------------------------------------------------------------------------------
class OrganizationBase(ApiModel):
    legal_name: str | None = None
    cage_code: str | None = None
    uei: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    website: str | None = None
    primary_contact_name: str | None = None
    primary_contact_email: str | None = None
    primary_contact_phone: str | None = None
    it_contact_name: str | None = None
    it_contact_email: str | None = None
    it_contact_phone: str | None = None
    industry: str | None = None
    employee_count: int | None = Field(default=None, ge=0)
    notes: str | None = None


class OrganizationUpsert(OrganizationBase):
    name: str = Field(min_length=1, max_length=200)


class OrganizationRead(OrganizationBase):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------------------------
# Systems
# --------------------------------------------------------------------------------------------
class ScoreSummary(ApiModel):
    """Lightweight per-system summary derived from implementation statuses."""

    met_count: int
    total: int


class SystemBase(ApiModel):
    description: str | None = None
    environment: Environment = Environment.on_prem
    boundary_description: str | None = None
    cui_types: str | None = None
    cui_description: str | None = None
    data_flow_description: str | None = None
    status: SystemStatus = SystemStatus.draft


class SystemCreate(SystemBase):
    name: str = Field(min_length=1, max_length=200)


class SystemUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    environment: Environment | None = None
    boundary_description: str | None = None
    cui_types: str | None = None
    cui_description: str | None = None
    data_flow_description: str | None = None
    status: SystemStatus | None = None


class SystemRead(SystemBase):
    id: int
    organization_id: int
    name: str
    created_at: datetime
    updated_at: datetime


class SystemListItem(SystemRead):
    score_summary: ScoreSummary
    asset_count: int = 0


# --------------------------------------------------------------------------------------------
# Assets
# --------------------------------------------------------------------------------------------
class AssetBase(ApiModel):
    asset_type: AssetType = AssetType.workstation
    category: AssetCategory = AssetCategory.cui
    category_rationale: str | None = None
    os_family: str | None = None
    os_name: str | None = None
    os_version: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    location: str | None = None
    owner: str | None = None
    description: str | None = None
    serial_number: str | None = None
    needs_review: bool = False


class AssetCreate(AssetBase):
    name: str = Field(min_length=1, max_length=200)


class AssetUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    asset_type: AssetType | None = None
    category: AssetCategory | None = None
    category_rationale: str | None = None
    os_family: str | None = None
    os_name: str | None = None
    os_version: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    location: str | None = None
    owner: str | None = None
    description: str | None = None
    serial_number: str | None = None
    needs_review: bool | None = None


class AssetRead(AssetBase):
    id: int
    system_id: int
    name: str
    agent_platform: str | None = None
    agent_version: str | None = None
    agent_last_seen: datetime | None = None
    agent_last_report_id: int | None = None
    created_at: datetime
    updated_at: datetime


class CheckResultRead(ApiModel):
    id: int
    report_id: int
    asset_id: int
    system_id: int
    check_id: str
    title: str | None = None
    status: str
    observed: str | None = None
    expected: str | None = None
    details: Any = None
    error: str | None = None
    collected_at: datetime | None = None
    control_ids: list[str] = []
    objective_ids: list[str] = []
    is_latest: bool = True
    created_at: datetime


class AgentReportRead(ApiModel):
    """Report history entry (never includes ``raw_json``)."""

    id: int
    asset_id: int
    system_id: int
    agent_version: str | None = None
    platform: str | None = None
    hostname: str | None = None
    collected_at: datetime | None = None
    received_at: datetime
    check_count: int = 0
    fail_count: int = 0
    created_at: datetime


# --------------------------------------------------------------------------------------------
# Providers and shared responsibility
# --------------------------------------------------------------------------------------------
class ProviderBase(ApiModel):
    kind: ProviderKind = ProviderKind.csp
    service_description: str | None = None
    fedramp_status: FedrampStatus = FedrampStatus.none
    crm_reference: str | None = None
    contact: str | None = None
    notes: str | None = None


class ProviderCreate(ProviderBase):
    name: str = Field(min_length=1, max_length=200)


class ProviderUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    kind: ProviderKind | None = None
    service_description: str | None = None
    fedramp_status: FedrampStatus | None = None
    crm_reference: str | None = None
    contact: str | None = None
    notes: str | None = None


class ProviderRead(ProviderBase):
    id: int
    organization_id: int
    name: str
    created_at: datetime
    updated_at: datetime


class ResponsibilityRowIn(ApiModel):
    control_id: str = Field(min_length=3, max_length=16)
    model: ResponsibilityModel = ResponsibilityModel.not_covered
    provider_responsibility: str | None = None
    customer_responsibility: str | None = None
    inherited: bool = False


class ResponsibilityRowRead(ApiModel):
    """One matrix row. ``id`` is ``None`` for controls the provider has no stored row for."""

    id: int | None = None
    provider_id: int
    control_id: str
    control_name: str = ""
    cmmc_id: str | None = None
    family_id: str | None = None
    family_abbr: str | None = None
    weight: int = 0
    model: ResponsibilityModel = ResponsibilityModel.not_covered
    provider_responsibility: str | None = None
    customer_responsibility: str | None = None
    inherited: bool = False
    updated_at: datetime | None = None


class ApplyTemplateRequest(ApiModel):
    template_id: str = Field(min_length=1, max_length=64)


class ApplyTemplateResponse(ApiModel):
    template_id: str
    template_name: str
    applied: int
    skipped_control_ids: list[str] = []
    disclaimer: str | None = None
    rows: list[ResponsibilityRowRead]


# --------------------------------------------------------------------------------------------
# Controls / implementations
# --------------------------------------------------------------------------------------------
class ImplementationRead(ApiModel):
    id: int
    system_id: int
    control_id: str
    status: ImplementationStatus
    responsibility: Responsibility
    provider_id: int | None = None
    implementation_narrative: str | None = None
    customer_responsibility: str | None = None
    provider_responsibility: str | None = None
    na_justification: str | None = None
    partial_credit: PartialCredit
    assessed_at: datetime | None = None
    assessed_by: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ImplementationUpdate(ApiModel):
    """Partial update: only fields present in the body are changed."""

    status: ImplementationStatus | None = None
    responsibility: Responsibility | None = None
    provider_id: int | None = None
    implementation_narrative: str | None = None
    customer_responsibility: str | None = None
    provider_responsibility: str | None = None
    na_justification: str | None = None
    partial_credit: PartialCredit | None = None
    assessed_at: datetime | None = None
    assessed_by: str | None = None
    notes: str | None = None

    @field_validator("assessed_at")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return _ensure_utc(value)


class ObjectiveCounts(ApiModel):
    met: int = 0
    not_met: int = 0
    not_applicable: int = 0
    unknown: int = 0
    total: int = 0


class CheckSummary(ApiModel):
    """Latest agent check results touching a control, across the system's assets."""

    total: int = 0
    passing: int = 0
    failing: int = 0
    errors: int = 0
    info: int = 0
    not_applicable: int = 0
    assets: int = 0
    last_collected_at: datetime | None = None


class ControlListItem(ApiModel):
    control: CatalogControlSummary
    implementation: ImplementationRead
    objective_counts: ObjectiveCounts
    evidence_count: int = 0
    check_summary: CheckSummary | None = None
    open_poam_count: int = 0
    warnings: list[str] = []


class ObjectiveRead(ApiModel):
    id: int | None = None
    objective_id: str
    letter: str | None = None
    text: str = ""
    status: ObjectiveStatus = ObjectiveStatus.unknown
    notes: str | None = None
    updated_at: datetime | None = None


class ObjectiveUpdateItem(ApiModel):
    objective_id: str = Field(min_length=5, max_length=24)
    status: ObjectiveStatus
    notes: str | None = None


class EvidenceLinkRead(ApiModel):
    id: int
    evidence_id: int
    control_id: str
    objective_id: str | None = None


class EvidenceRead(ApiModel):
    id: int
    system_id: int
    title: str
    kind: EvidenceKind
    description: str | None = None
    file_name: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    collected_at: datetime | None = None
    expires_at: datetime | None = None
    expired: bool = False
    source: EvidenceSource
    asset_id: int | None = None
    check_id: str | None = None
    check_status: str | None = None
    links: list[EvidenceLinkRead] = []
    created_at: datetime
    updated_at: datetime


class PoamMilestoneRead(ApiModel):
    id: int
    poam_item_id: int
    description: str
    due_date: date | None = None
    completed_at: datetime | None = None
    position: int = 0
    created_at: datetime
    updated_at: datetime


class PoamItemRead(ApiModel):
    id: int
    system_id: int
    control_id: str
    title: str
    weakness_description: str | None = None
    source: PoamSource
    risk_level: RiskLevel
    status: PoamStatus
    owner: str | None = None
    identified_at: date | None = None
    scheduled_completion: date | None = None
    actual_completion: date | None = None
    remediation_plan: str | None = None
    resources_required: str | None = None
    cost_estimate: str | None = None
    check_id: str | None = None
    asset_id: int | None = None
    notes: str | None = None
    milestones: list[PoamMilestoneRead] = []
    created_at: datetime
    updated_at: datetime


class ControlDetail(ApiModel):
    control: CatalogControlFull
    implementation: ImplementationRead
    provider: ProviderRead | None = None
    responsibility_row: ResponsibilityRowRead | None = None
    objectives: list[ObjectiveRead]
    objective_counts: ObjectiveCounts
    evidence: list[EvidenceRead] = []
    check_results: list[CheckResultRead] = []
    check_summary: CheckSummary | None = None
    poam_items: list[PoamItemRead] = []
    open_poam_count: int = 0
    warnings: list[str] = []


class BulkControlItem(ApiModel):
    control_id: str = Field(min_length=3, max_length=16)
    status: ImplementationStatus | None = None
    responsibility: Responsibility | None = None
    provider_id: int | None = None


class BulkControlResponse(ApiModel):
    updated: int
    implementations: list[ImplementationRead]


# --------------------------------------------------------------------------------------------
# Activity
# --------------------------------------------------------------------------------------------
class ActivityRead(ApiModel):
    id: int
    system_id: int | None = None
    actor: str
    action: str
    entity_type: str
    entity_id: int | None = None
    summary: str
    created_at: datetime


# --------------------------------------------------------------------------------------------
# Agent reports (ARCHITECTURE.md §3) and ingestion
# --------------------------------------------------------------------------------------------
class AgentInfoIn(ApiModel):
    """Identification of the collector that produced a report."""

    model_config = ConfigDict(extra="ignore")

    name: str = "bulwark-agent"
    version: str | None = None
    platform: str | None = None


class AssetInfoIn(ApiModel):
    """The device a report describes."""

    model_config = ConfigDict(extra="ignore")

    hostname: str = Field(min_length=1, max_length=200)
    fqdn: str | None = None
    os_family: str | None = None
    os_name: str | None = None
    os_version: str | None = None
    arch: str | None = None
    domain: str | None = None
    serial_number: str | None = None
    ip_addresses: list[str] = []
    mac_addresses: list[str] = []
    logged_in_users: list[str] = []


class CheckIn(ApiModel):
    """One automated check result as sent by an agent."""

    model_config = ConfigDict(extra="ignore")

    check_id: str = Field(min_length=1, max_length=128)
    status: CheckStatus
    observed: str | None = None
    expected: str | None = None
    details: Any = None
    error: str | None = None


class AgentReportIn(ApiModel):
    """The report body posted to ``/api/agents/report``."""

    model_config = ConfigDict(extra="ignore")

    schema_version: int = 1
    agent: AgentInfoIn = AgentInfoIn()
    asset: AssetInfoIn
    collected_at: datetime | None = None
    checks: list[CheckIn] = []
    inventory: dict[str, Any] = {}


class IngestResponse(ApiModel):
    ok: bool = True
    asset_id: int
    system_id: int
    checks_ingested: int
    findings: int
    poam_created: int = 0
    unknown_checks: list[str] = []
    message: str = ""


class EnrollmentInstall(ApiModel):
    windows: str
    linux: str
    macos: str


class EnrollmentInfo(ApiModel):
    system_id: int
    enrollment_key: str
    server_url: str
    install: EnrollmentInstall


class AgentStatusItem(ApiModel):
    asset_id: int
    asset_name: str
    hostname: str | None = None
    category: AssetCategory
    platform: str | None = None
    agent_version: str | None = None
    last_seen: datetime | None = None
    stale: bool = True
    pass_count: int = 0
    fail_count: int = 0
    error_count: int = 0
    info_count: int = 0
    not_applicable_count: int = 0


class FindingAsset(ApiModel):
    asset_id: int
    asset_name: str
    status: str
    observed: str | None = None
    collected_at: datetime | None = None


class FindingItem(ApiModel):
    """A failing automated check, grouped by the control it maps to."""

    control_id: str
    cmmc_id: str | None = None
    control_name: str = ""
    weight: int = 0
    check_id: str
    check_title: str = ""
    expected: str | None = None
    remediation: str | None = None
    objective_ids: list[str] = []
    asset_count: int = 0
    assets: list[FindingAsset] = []
    poam_item_id: int | None = None


# --------------------------------------------------------------------------------------------
# POA&M
# --------------------------------------------------------------------------------------------
class PoamMilestoneCreate(ApiModel):
    description: str = Field(min_length=1, max_length=500)
    due_date: date | None = None
    position: int | None = None
    completed_at: datetime | None = None


class PoamMilestoneUpdate(ApiModel):
    description: str | None = Field(default=None, min_length=1, max_length=500)
    due_date: date | None = None
    position: int | None = None
    completed: bool | None = None
    """``true`` stamps ``completed_at`` now, ``false`` clears it."""


class PoamItemCreate(ApiModel):
    control_id: str = Field(min_length=3, max_length=16)
    title: str = Field(min_length=1, max_length=300)
    weakness_description: str | None = None
    source: PoamSource = PoamSource.self_assessment
    risk_level: RiskLevel | None = None
    owner: str | None = None
    identified_at: date | None = None
    scheduled_completion: date | None = None
    remediation_plan: str | None = None
    resources_required: str | None = None
    cost_estimate: str | None = None
    check_id: str | None = None
    asset_id: int | None = None
    notes: str | None = None
    milestones: list[PoamMilestoneCreate] = []


class PoamItemUpdate(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    weakness_description: str | None = None
    source: PoamSource | None = None
    risk_level: RiskLevel | None = None
    owner: str | None = None
    identified_at: date | None = None
    scheduled_completion: date | None = None
    actual_completion: date | None = None
    remediation_plan: str | None = None
    resources_required: str | None = None
    cost_estimate: str | None = None
    notes: str | None = None


class PoamTransitionRequest(ApiModel):
    status: PoamStatus
    note: str | None = None


# --------------------------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------------------------
class EvidenceUpdate(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    kind: EvidenceKind | None = None
    description: str | None = None
    collected_at: datetime | None = None
    expires_at: datetime | None = None


class EvidenceLinkCreate(ApiModel):
    control_id: str = Field(min_length=3, max_length=16)
    objective_id: str | None = Field(default=None, max_length=24)


# --------------------------------------------------------------------------------------------
# Scoring and readiness
# --------------------------------------------------------------------------------------------
class ScoreDeduction(ApiModel):
    control_id: str
    cmmc_id: str | None = None
    name: str = ""
    weight: int
    deducted: int
    status: str
    reason: str | None = None


class ScoreWarning(ApiModel):
    control_id: str
    messages: list[str] = []


class ScoreFamily(ApiModel):
    id: str
    abbr: str = ""
    name: str = ""
    met: int = 0
    total: int = 0
    deducted_points: int = 0


class ScoreResult(ApiModel):
    """SPRS score and eligibility (ARCHITECTURE.md §4.4)."""

    sprs_score: int
    max_score: int = 110
    min_score: int = -203
    met_count: int
    not_met_count: int
    na_count: int
    total: int
    readiness_pct: float
    assessment_blocked: bool = False
    conditional_eligible: bool = False
    conditional_blockers: list[str] = []
    final_ready: bool = False
    deductions: list[ScoreDeduction] = []
    warnings: list[ScoreWarning] = []
    families: list[ScoreFamily] = []
    by_status: dict[str, int] = {}


class NextAction(ApiModel):
    control_id: str
    cmmc_id: str | None = None
    name: str = ""
    family_abbr: str = ""
    weight: int
    points_recoverable: int
    status: str
    objectives_outstanding: int
    poam_allowed: bool = False
    reason: str | None = None
    guidance: str = ""


class CoverageStat(ApiModel):
    covered: int = 0
    total: int = 0
    pct: float = 0.0


class Contradiction(ApiModel):
    """A requirement recorded as met that a live automated check disproves."""

    control_id: str
    cmmc_id: str | None = None
    name: str = ""
    weight: int = 0
    recorded_status: str
    failing_checks: list[str] = []


class ReadinessResponse(ApiModel):
    system_id: int
    score: ScoreResult
    evidence_coverage: CoverageStat
    automated_coverage: CoverageStat
    stale_evidence_count: int = 0
    overdue_poam_count: int = 0
    aging_poam_count: int = 0
    open_poam_count: int = 0
    findings_count: int = 0
    assets_needing_review: int = 0
    assets_total: int = 0
    agents_reporting: int = 0
    agents_stale: int = 0
    inheritance_gaps: list[str] = []
    contradictions: list[Contradiction] = []
    contradiction_count: int = 0
    next_actions: list[NextAction] = []
    generated_at: datetime


class ScoreSnapshotRead(ApiModel):
    id: int
    system_id: int
    taken_at: datetime
    sprs_score: int
    met_count: int
    total_count: int
    readiness_pct: float
    conditional_eligible: bool = False
