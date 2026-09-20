"""SQLModel tables (ARCHITECTURE.md §4.2).

Conventions
-----------
* Every table has an integer ``id`` primary key plus ``created_at``/``updated_at`` stored as UTC.
* Enumerations are ``str`` enums whose *names equal their values*; the API accepts and returns the
  plain string form (``"implemented"``), never the enum name.
* Foreign keys carry ``ON DELETE`` semantics at the database level (``PRAGMA foreign_keys=ON``)
  *and* the routers delete children explicitly, so cascades work even without the pragma.
* Control ids are plain (``3.1.1``); objective ids use the 800-171A form (``3.1.1[a]``).
"""

from __future__ import annotations

import secrets
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, SQLModel


# --------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------
def utcnow() -> datetime:
    """Timezone-aware current UTC time (microseconds trimmed for stable serialisation)."""
    return datetime.now(UTC).replace(microsecond=0)


def generate_enrollment_key() -> str:
    """Random 32-character hex enrollment key for agents."""
    return secrets.token_hex(16)


class UTCDateTime(TypeDecorator):
    """Store datetimes as naive UTC in SQLite and hand back timezone-aware UTC values."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"expected datetime, got {type(value).__name__}")
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def fk_column(
    target: str, *, ondelete: str = "CASCADE", nullable: bool = False, index: bool = True
) -> Column:
    """Build an integer foreign-key column with explicit ON DELETE behaviour."""
    return Column(Integer, ForeignKey(target, ondelete=ondelete), nullable=nullable, index=index)


# --------------------------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------------------------
class Environment(StrEnum):
    on_prem = "on_prem"
    cloud = "cloud"
    hybrid = "hybrid"


class SystemStatus(StrEnum):
    draft = "draft"
    active = "active"
    retired = "retired"


class AssetType(StrEnum):
    workstation = "workstation"
    server = "server"
    network_device = "network_device"
    mobile = "mobile"
    printer = "printer"
    iot_ot = "iot_ot"
    cloud_service = "cloud_service"
    application = "application"
    removable_media = "removable_media"
    facility = "facility"
    other = "other"


class AssetCategory(StrEnum):
    cui = "cui"
    security_protection = "security_protection"
    contractor_risk_managed = "contractor_risk_managed"
    specialized = "specialized"
    out_of_scope = "out_of_scope"


IN_SCOPE_ASSET_CATEGORIES = frozenset(
    {
        AssetCategory.cui,
        AssetCategory.security_protection,
        AssetCategory.contractor_risk_managed,
        AssetCategory.specialized,
    }
)


class ProviderKind(StrEnum):
    csp = "csp"
    msp = "msp"
    mssp = "mssp"
    other = "other"


class FedrampStatus(StrEnum):
    none = "none"
    li_saas = "li_saas"
    low = "low"
    moderate = "moderate"
    high = "high"
    equivalent = "equivalent"
    il4 = "il4"
    il5 = "il5"


class ResponsibilityModel(StrEnum):
    provider = "provider"
    customer = "customer"
    shared = "shared"
    not_covered = "not_covered"


class ImplementationStatus(StrEnum):
    not_implemented = "not_implemented"
    planned = "planned"
    partially_implemented = "partially_implemented"
    implemented = "implemented"
    not_applicable = "not_applicable"


MET_STATUSES = frozenset({ImplementationStatus.implemented, ImplementationStatus.not_applicable})


class Responsibility(StrEnum):
    customer = "customer"
    provider = "provider"
    shared = "shared"
    inherited = "inherited"


class PartialCredit(StrEnum):
    none = "none"
    mfa_partial = "mfa_partial"
    encryption_non_fips = "encryption_non_fips"


PARTIAL_CREDIT_CONTROLS: dict[str, PartialCredit] = {
    "3.5.3": PartialCredit.mfa_partial,
    "3.13.11": PartialCredit.encryption_non_fips,
}
"""The only controls that may carry a partial-credit flag (DoD Assessment Methodology)."""


class ObjectiveStatus(StrEnum):
    met = "met"
    not_met = "not_met"
    not_applicable = "not_applicable"
    unknown = "unknown"


class PoamSource(StrEnum):
    self_assessment = "self_assessment"
    agent = "agent"
    c3pao = "c3pao"
    dibcac = "dibcac"
    audit = "audit"
    other = "other"


class RiskLevel(StrEnum):
    low = "low"
    moderate = "moderate"
    high = "high"
    critical = "critical"


class PoamStatus(StrEnum):
    open = "open"
    in_progress = "in_progress"
    completed = "completed"
    risk_accepted = "risk_accepted"
    closed = "closed"


OPEN_POAM_STATUSES = frozenset({PoamStatus.open, PoamStatus.in_progress})


class EvidenceKind(StrEnum):
    document = "document"
    policy = "policy"
    procedure = "procedure"
    screenshot = "screenshot"
    config_export = "config_export"
    log = "log"
    agent_check = "agent_check"
    attestation = "attestation"
    other = "other"


class EvidenceSource(StrEnum):
    manual = "manual"
    agent = "agent"


class CheckStatus(StrEnum):
    passed = "pass"
    fail = "fail"
    error = "error"
    not_applicable = "not_applicable"
    info = "info"


class Platform(StrEnum):
    windows = "windows"
    linux = "linux"
    macos = "macos"


# --------------------------------------------------------------------------------------------
# Base
# --------------------------------------------------------------------------------------------
class Timestamped(SQLModel):
    """Shared ``id`` / ``created_at`` / ``updated_at`` columns."""

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime, nullable=False)
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_type=UTCDateTime,
        nullable=False,
        sa_column_kwargs={"onupdate": utcnow},
    )

    def touch(self) -> None:
        """Bump ``updated_at`` explicitly (the column also updates itself on UPDATE)."""
        self.updated_at = utcnow()


# --------------------------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------------------------
class Organization(Timestamped, table=True):
    __tablename__ = "organization"

    name: str = Field(index=True)
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
    employee_count: int | None = None
    notes: str | None = None


class System(Timestamped, table=True):
    __tablename__ = "system"

    organization_id: int = Field(sa_column=fk_column("organization.id"))
    name: str = Field(index=True)
    description: str | None = None
    environment: Environment = Field(default=Environment.on_prem)
    boundary_description: str | None = None
    cui_types: str | None = None
    cui_description: str | None = None
    data_flow_description: str | None = None
    enrollment_key: str = Field(
        default_factory=generate_enrollment_key, unique=True, index=True, max_length=64
    )
    status: SystemStatus = Field(default=SystemStatus.draft)


class Asset(Timestamped, table=True):
    __tablename__ = "asset"
    __table_args__ = (Index("ix_asset_system_name", "system_id", "name"),)

    system_id: int = Field(sa_column=fk_column("system.id"))
    name: str
    asset_type: AssetType = Field(default=AssetType.workstation)
    category: AssetCategory = Field(default=AssetCategory.cui)
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
    needs_review: bool = Field(default=False)
    agent_platform: str | None = None
    agent_version: str | None = None
    agent_last_seen: datetime | None = Field(default=None, sa_type=UTCDateTime, nullable=True)
    agent_last_report_id: int | None = None


class Provider(Timestamped, table=True):
    __tablename__ = "provider"

    organization_id: int = Field(sa_column=fk_column("organization.id"))
    name: str = Field(index=True)
    kind: ProviderKind = Field(default=ProviderKind.csp)
    service_description: str | None = None
    fedramp_status: FedrampStatus = Field(default=FedrampStatus.none)
    crm_reference: str | None = None
    contact: str | None = None
    notes: str | None = None


class ResponsibilityRow(Timestamped, table=True):
    __tablename__ = "responsibility_row"
    __table_args__ = (
        UniqueConstraint("provider_id", "control_id", name="uq_responsibility_row_provider_control"),
    )

    provider_id: int = Field(sa_column=fk_column("provider.id"))
    control_id: str = Field(index=True, max_length=16)
    model: ResponsibilityModel = Field(default=ResponsibilityModel.not_covered)
    provider_responsibility: str | None = None
    customer_responsibility: str | None = None
    inherited: bool = Field(default=False)


class ControlImplementation(Timestamped, table=True):
    __tablename__ = "control_implementation"
    __table_args__ = (
        UniqueConstraint("system_id", "control_id", name="uq_control_implementation_system_control"),
    )

    system_id: int = Field(sa_column=fk_column("system.id"))
    control_id: str = Field(index=True, max_length=16)
    status: ImplementationStatus = Field(default=ImplementationStatus.not_implemented)
    responsibility: Responsibility = Field(default=Responsibility.customer)
    provider_id: int | None = Field(
        default=None, sa_column=fk_column("provider.id", ondelete="SET NULL", nullable=True)
    )
    implementation_narrative: str | None = None
    customer_responsibility: str | None = None
    provider_responsibility: str | None = None
    na_justification: str | None = None
    partial_credit: PartialCredit = Field(default=PartialCredit.none)
    assessed_at: datetime | None = Field(default=None, sa_type=UTCDateTime, nullable=True)
    assessed_by: str | None = None
    notes: str | None = None


class ObjectiveAssessment(Timestamped, table=True):
    __tablename__ = "objective_assessment"
    __table_args__ = (
        UniqueConstraint("implementation_id", "objective_id", name="uq_objective_assessment_impl_objective"),
    )

    implementation_id: int = Field(sa_column=fk_column("control_implementation.id"))
    objective_id: str = Field(index=True, max_length=24)
    status: ObjectiveStatus = Field(default=ObjectiveStatus.unknown)
    notes: str | None = None


class PoamItem(Timestamped, table=True):
    __tablename__ = "poam_item"
    __table_args__ = (Index("ix_poam_item_system_control", "system_id", "control_id"),)

    system_id: int = Field(sa_column=fk_column("system.id"))
    control_id: str = Field(index=True, max_length=16)
    title: str
    weakness_description: str | None = None
    source: PoamSource = Field(default=PoamSource.self_assessment)
    risk_level: RiskLevel = Field(default=RiskLevel.moderate)
    status: PoamStatus = Field(default=PoamStatus.open)
    owner: str | None = None
    identified_at: date | None = None
    scheduled_completion: date | None = None
    actual_completion: date | None = None
    remediation_plan: str | None = None
    resources_required: str | None = None
    cost_estimate: str | None = None
    check_id: str | None = Field(default=None, max_length=128)
    asset_id: int | None = Field(
        default=None, sa_column=fk_column("asset.id", ondelete="SET NULL", nullable=True)
    )
    notes: str | None = None


class PoamMilestone(Timestamped, table=True):
    __tablename__ = "poam_milestone"

    poam_item_id: int = Field(sa_column=fk_column("poam_item.id"))
    description: str
    due_date: date | None = None
    completed_at: datetime | None = Field(default=None, sa_type=UTCDateTime, nullable=True)
    position: int = Field(default=0)


class Evidence(Timestamped, table=True):
    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_asset_check", "asset_id", "check_id"),)

    system_id: int = Field(sa_column=fk_column("system.id"))
    title: str
    kind: EvidenceKind = Field(default=EvidenceKind.document)
    description: str | None = None
    file_name: str | None = None
    file_path: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    collected_at: datetime | None = Field(default=None, sa_type=UTCDateTime, nullable=True)
    expires_at: datetime | None = Field(default=None, sa_type=UTCDateTime, nullable=True)
    source: EvidenceSource = Field(default=EvidenceSource.manual)
    asset_id: int | None = Field(
        default=None, sa_column=fk_column("asset.id", ondelete="SET NULL", nullable=True)
    )
    check_id: str | None = Field(default=None, max_length=128)
    check_status: str | None = None


class EvidenceLink(Timestamped, table=True):
    __tablename__ = "evidence_link"
    __table_args__ = (
        UniqueConstraint("evidence_id", "control_id", "objective_id", name="uq_evidence_link_target"),
    )

    evidence_id: int = Field(sa_column=fk_column("evidence.id"))
    control_id: str = Field(index=True, max_length=16)
    objective_id: str | None = Field(default=None, index=True, max_length=24)


class AgentReport(Timestamped, table=True):
    __tablename__ = "agent_report"

    asset_id: int = Field(sa_column=fk_column("asset.id"))
    system_id: int = Field(sa_column=fk_column("system.id"))
    agent_version: str | None = None
    platform: str | None = None
    hostname: str | None = None
    collected_at: datetime | None = Field(default=None, sa_type=UTCDateTime, nullable=True)
    received_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime, nullable=False)
    raw_json: str = Field(default="{}")
    check_count: int = Field(default=0)
    fail_count: int = Field(default=0)


class CheckResult(Timestamped, table=True):
    __tablename__ = "check_result"
    __table_args__ = (
        Index("ix_check_result_asset_check_latest", "asset_id", "check_id", "is_latest"),
        Index("ix_check_result_system_latest", "system_id", "is_latest"),
    )

    report_id: int = Field(sa_column=fk_column("agent_report.id"))
    asset_id: int = Field(sa_column=fk_column("asset.id"))
    system_id: int = Field(sa_column=fk_column("system.id"))
    check_id: str = Field(index=True, max_length=128)
    title: str | None = None
    status: str = Field(default=CheckStatus.info.value)
    observed: str | None = None
    expected: str | None = None
    details_json: str | None = None
    error: str | None = None
    collected_at: datetime | None = Field(default=None, sa_type=UTCDateTime, nullable=True)
    control_ids_json: str = Field(default="[]")
    objective_ids_json: str = Field(default="[]")
    is_latest: bool = Field(default=True)


class ScoreSnapshot(Timestamped, table=True):
    __tablename__ = "score_snapshot"

    system_id: int = Field(sa_column=fk_column("system.id"))
    taken_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime, nullable=False)
    sprs_score: int
    met_count: int
    total_count: int
    readiness_pct: float
    conditional_eligible: bool = Field(default=False)
    details_json: str = Field(default="{}")


class ActivityLog(Timestamped, table=True):
    __tablename__ = "activity_log"

    system_id: int | None = Field(
        default=None, sa_column=fk_column("system.id", ondelete="SET NULL", nullable=True)
    )
    actor: str
    action: str = Field(index=True)
    entity_type: str = Field(index=True)
    entity_id: int | None = None
    summary: str


ALL_TABLES: tuple[type[SQLModel], ...] = (
    Organization,
    System,
    Asset,
    Provider,
    ResponsibilityRow,
    ControlImplementation,
    ObjectiveAssessment,
    PoamItem,
    PoamMilestone,
    Evidence,
    EvidenceLink,
    AgentReport,
    CheckResult,
    ScoreSnapshot,
    ActivityLog,
)
