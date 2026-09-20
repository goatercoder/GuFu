"""Demo data: a realistic 40-person machine shop part-way through CMMC Level 2 readiness.

Idempotent: running it twice changes nothing. It goes through the same code paths the API uses,
including agent ingestion, so findings, evidence and automatic POA&M items are real.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session, select

from . import catalog
from .activity import log_activity
from .config import get_settings
from .evidence_rules import ingest_report
from .models import (
    Asset,
    AssetCategory,
    AssetType,
    Environment,
    Evidence,
    EvidenceKind,
    EvidenceLink,
    EvidenceSource,
    FedrampStatus,
    ImplementationStatus,
    ObjectiveAssessment,
    ObjectiveStatus,
    Organization,
    PartialCredit,
    PoamItem,
    PoamMilestone,
    PoamSource,
    PoamStatus,
    Provider,
    ProviderKind,
    Responsibility,
    ResponsibilityModel,
    ResponsibilityRow,
    RiskLevel,
    System,
    SystemStatus,
    utcnow,
)
from .services import seed_implementations

DEMO_ORG = "Precision Machining LLC"
DEMO_SYSTEM = "Shop CUI Enclave"

#: Requirements the demo shop has genuinely not done yet, by status.
#: The shop has done most of the work. What is left is the expensive, specialist end: vulnerability
#: scanning, monitoring, formal assessment, application allow-listing and FIPS validation.
NOT_IMPLEMENTED = ["3.11.2", "3.12.1", "3.14.6", "3.4.8", "3.11.3", "3.3.6"]
PLANNED = ["3.13.16", "3.6.3"]
PARTIAL = ["3.5.3", "3.13.11"]
NOT_APPLICABLE = {
    "3.13.14": "The shop does not use Voice over IP: the phone system is an analogue PBX with no "
               "connection to the CUI enclave, confirmed with the telephone vendor on 2026-02-11.",
    "3.5.11": "No obscured feedback requirement applies to the CNC controllers, which have no "
              "interactive authentication prompt; all other systems obscure feedback by default.",
    "3.10.6": "No alternate work sites are authorized for CUI. Remote work is prohibited by the "
              "acceptable use policy and enforced by conditional access rules.",
}

ASSETS = [
    ("ENG-CAD-01", AssetType.workstation, AssetCategory.cui, "windows", "Windows 11 Pro", "23H2",
     "10.20.1.21", "Engineering", "M. Alvarez", "CAD workstation used for customer drawings", False),
    ("ENG-CAD-02", AssetType.workstation, AssetCategory.cui, "windows", "Windows 11 Pro", "23H2",
     "10.20.1.22", "Engineering", "D. Kowalski", "CAD workstation used for customer drawings", False),
    ("EST-PC-01", AssetType.workstation, AssetCategory.cui, "windows", "Windows 11 Pro", "23H2",
     "10.20.1.31", "Front office", "R. Patel", "Estimating and quoting, receives RFQ packages", False),
    ("SHOP-FS-01", AssetType.server, AssetCategory.cui, "windows", "Windows Server 2022", "21H2",
     "10.20.1.10", "Server closet", "IT", "File server holding job folders and drawings", False),
    ("SHOP-CNC-01", AssetType.iot_ot, AssetCategory.specialized, "windows", "Windows 10 IoT LTSC",
     "21H2", "10.20.9.11", "Shop floor bay 1", "Production",
     "Haas control PC; specialized asset, cannot run an agent continuously", False),
    ("SHOP-CNC-02", AssetType.iot_ot, AssetCategory.specialized, "windows", "Windows 10 IoT LTSC",
     "21H2", "10.20.9.12", "Shop floor bay 2", "Production",
     "Mazak control PC; specialized asset on the isolated machine VLAN", False),
    ("FW-EDGE-01", AssetType.network_device, AssetCategory.security_protection, "other",
     "FortiGate 60F", "7.4", "10.20.0.1", "Server closet", "MSP",
     "Perimeter firewall, VPN concentrator and IPS for the enclave", False),
    ("SW-CORE-01", AssetType.network_device, AssetCategory.security_protection, "other",
     "Managed switch", "3.2", "10.20.0.2", "Server closet", "MSP",
     "Core switch enforcing the VLAN separation between office, shop floor and guest", False),
    ("RMM-AGENT", AssetType.application, AssetCategory.security_protection, "other",
     "MSP remote monitoring and management", "", "", "Cloud", "MSP",
     "Patching, endpoint management and alerting operated by the MSP", False),
    ("M365-GCCH", AssetType.cloud_service, AssetCategory.cui, "other",
     "Microsoft 365 GCC High", "", "", "Cloud", "IT",
     "Email, SharePoint, OneDrive and Teams tenant that stores CUI", False),
    ("QA-TABLET-01", AssetType.mobile, AssetCategory.contractor_risk_managed, "other", "iPad", "17",
     "10.20.2.41", "Quality lab", "Quality",
     "Inspection checklists only; policy prohibits CUI, not connected to the CUI VLAN", False),
    ("MKT-LAPTOP-01", AssetType.workstation, AssetCategory.out_of_scope, "windows", "Windows 11 Home",
     "23H2", "10.20.3.51", "Front office", "Marketing",
     "Marketing laptop on the guest VLAN with no route to the enclave and no CUI access; "
     "excluded from the assessment scope", False),
]


def _get_or_create_org(session: Session) -> tuple[Organization, bool]:
    existing = session.exec(select(Organization).where(Organization.name == DEMO_ORG)).first()
    if existing:
        return existing, False
    org = Organization(
        name=DEMO_ORG,
        legal_name="Precision Machining LLC",
        cage_code="1AB23",
        uei="PM7Q4KX9TL63",
        address="1420 Foundry Road",
        city="Waukesha",
        state="WI",
        zip="53186",
        website="https://precisionmachining.example",
        primary_contact_name="Janet Rowe",
        primary_contact_email="jrowe@precisionmachining.example",
        primary_contact_phone="+1 262 555 0143",
        it_contact_name="Tom Byrne",
        it_contact_email="tbyrne@precisionmachining.example",
        it_contact_phone="+1 262 555 0188",
        industry="Precision machining (NAICS 332710)",
        employee_count=41,
        notes="Tier 2 supplier of machined aerospace components; receives CUI drawings from two primes.",
    )
    session.add(org)
    session.flush()
    return org, True


def _narrative(control: dict) -> str:
    """A short, specific implementation statement drawn from the catalog guidance."""
    guidance = control.get("guidance") or {}
    example = (guidance.get("machine_shop_example") or "").strip()
    if example:
        return example
    return (
        f"{DEMO_ORG} implements {control['cmmc_id']} across the {DEMO_SYSTEM} as described in the "
        "supporting policy and procedure documents."
    )


def _apply_statuses(session: Session, system: System) -> None:
    from .models import ControlImplementation

    impls = {
        impl.control_id: impl
        for impl in session.exec(
            select(ControlImplementation).where(ControlImplementation.system_id == system.id)
        ).all()
    }
    providers = {p.name: p for p in session.exec(select(Provider)).all()}
    msp = providers.get("Northshore Managed IT")
    tenant = providers.get("Microsoft 365 GCC High")
    today = date.today()

    for control_id, impl in impls.items():
        control = catalog.control(control_id) or {}
        if control_id in NOT_APPLICABLE:
            impl.status = ImplementationStatus.not_applicable
            impl.na_justification = NOT_APPLICABLE[control_id]
        elif control_id in NOT_IMPLEMENTED:
            impl.status = ImplementationStatus.not_implemented
        elif control_id in PLANNED:
            impl.status = ImplementationStatus.planned
            impl.implementation_narrative = (
                f"Planned for this fiscal year. {(control.get('guidance') or {}).get('summary', '')}"
            )
        elif control_id in PARTIAL:
            impl.status = ImplementationStatus.partially_implemented
            impl.implementation_narrative = _narrative(control)
        else:
            impl.status = ImplementationStatus.implemented
            impl.implementation_narrative = _narrative(control)
            impl.assessed_by = "Tom Byrne"
            impl.assessed_at = utcnow()

        family = control.get("family_id")
        if family in ("3.10",) or control_id in ("3.7.2", "3.7.3", "3.7.6"):
            if tenant is not None and control_id in ("3.10.1", "3.10.2"):
                impl.responsibility = Responsibility.shared
                impl.provider_id = tenant.id
        elif family in ("3.4", "3.14") and msp is not None:
            impl.responsibility = Responsibility.shared
            impl.provider_id = msp.id
            impl.provider_responsibility = (
                "Northshore Managed IT operates the tooling (RMM patching, Defender policy and alerting) "
                "and provides monthly reports."
            )
            impl.customer_responsibility = (
                "Precision Machining sets the policy and thresholds, reviews the monthly report and "
                "retains it as evidence."
            )
        elif family in ("3.13",) and tenant is not None and control_id in ("3.13.8", "3.13.16"):
            impl.responsibility = Responsibility.shared
            impl.provider_id = tenant.id

        if control_id == "3.5.3":
            impl.status = ImplementationStatus.partially_implemented
            impl.partial_credit = PartialCredit.mfa_partial
            impl.implementation_narrative = (
                "Multifactor authentication is enforced for all remote access through the firewall VPN "
                "and for the two administrative accounts in Entra ID. Local interactive logon for "
                "general users on shop-floor PCs is still password-only; hardware keys are on order."
            )
        if control_id == "3.13.11":
            impl.status = ImplementationStatus.partially_implemented
            impl.partial_credit = PartialCredit.encryption_non_fips
            impl.implementation_narrative = (
                "BitLocker protects every workstation and the file server, and the GCC High tenant "
                "encrypts data at rest and in transit. FIPS mode is not yet enabled on the "
                "workstations and the CMVP certificate numbers have not been recorded, so the "
                "cryptography in use is not yet demonstrably FIPS-validated."
            )
        impl.updated_at = utcnow()
        session.add(impl)
    session.flush()

    # Objective statuses follow the requirement status so the SSP and the score agree.
    rows = session.exec(
        select(ObjectiveAssessment).where(
            ObjectiveAssessment.implementation_id.in_([i.id for i in impls.values()])  # type: ignore[union-attr]
        )
    ).all()
    impl_by_id = {impl.id: impl for impl in impls.values()}
    for row in rows:
        impl = impl_by_id.get(row.implementation_id)
        if impl is None:
            continue
        if impl.status == ImplementationStatus.implemented:
            row.status = ObjectiveStatus.met
        elif impl.status == ImplementationStatus.not_applicable:
            row.status = ObjectiveStatus.not_applicable
        elif impl.status == ImplementationStatus.partially_implemented:
            # The last objective of a partially implemented requirement is the one outstanding.
            objectives = catalog.objective_ids_for(impl.control_id)
            row.status = (
                ObjectiveStatus.not_met if objectives and row.objective_id == objectives[-1]
                else ObjectiveStatus.met
            )
        else:
            row.status = ObjectiveStatus.not_met if impl.status == ImplementationStatus.planned else (
                ObjectiveStatus.unknown
            )
        session.add(row)
    _ = today


def _seed_providers(session: Session, org: Organization) -> None:
    if session.exec(select(Provider).where(Provider.organization_id == org.id)).first():
        return
    msp = Provider(
        organization_id=org.id,
        name="Northshore Managed IT",
        kind=ProviderKind.msp,
        service_description="Endpoint management, patching, backup, firewall administration and "
        "helpdesk for all 28 endpoints and the file server.",
        fedramp_status=FedrampStatus.none,
        crm_reference="Managed services agreement 2026-03 (Exhibit C: security responsibilities)",
        contact="support@northshore.example, +1 414 555 0110",
        notes="Handles CUI in the course of support; the MSP's own CMMC status is tracked in the "
        "supplier register.",
    )
    tenant = Provider(
        organization_id=org.id,
        name="Microsoft 365 GCC High",
        kind=ProviderKind.csp,
        service_description="Email, SharePoint, OneDrive, Teams, Entra ID, Intune and Defender for "
        "the CUI enclave.",
        fedramp_status=FedrampStatus.high,
        crm_reference="Microsoft CMMC customer responsibility documentation (retrieved 2026-04-02)",
        contact="Tenant admin: Tom Byrne",
    )
    session.add(msp)
    session.add(tenant)
    session.flush()

    for provider, template_id in ((msp, "generic_msp"), (tenant, "m365_gcc_high_starter")):
        template = catalog.load_crm_template(template_id)
        if template is None:
            continue
        for row in template.get("rows", []):
            if catalog.control(row.get("control_id", "")) is None:
                continue
            session.add(
                ResponsibilityRow(
                    provider_id=provider.id,
                    control_id=row["control_id"],
                    model=ResponsibilityModel(row.get("model", "not_covered")),
                    provider_responsibility=row.get("provider_responsibility"),
                    customer_responsibility=row.get("customer_responsibility"),
                    inherited=bool(row.get("inherited")),
                )
            )
    session.flush()


def _seed_assets(session: Session, system: System) -> None:
    if session.exec(select(Asset).where(Asset.system_id == system.id)).first():
        return
    for (name, asset_type, category, os_family, os_name, os_version, ip, location, owner,
         description, needs_review) in ASSETS:
        session.add(
            Asset(
                system_id=system.id,
                name=name,
                asset_type=asset_type,
                category=category,
                category_rationale=description if category != AssetCategory.cui else None,
                os_family=os_family,
                os_name=os_name,
                os_version=os_version,
                ip_address=ip or None,
                location=location,
                owner=owner,
                description=description,
                needs_review=needs_review,
            )
        )
    session.flush()


def _seed_evidence(session: Session, system: System) -> None:
    if session.exec(
        select(Evidence).where(Evidence.system_id == system.id, Evidence.source == EvidenceSource.manual)
    ).first():
        return
    settings = get_settings()
    directory = settings.evidence_dir / str(system.id)
    directory.mkdir(parents=True, exist_ok=True)
    today = date.today()
    documents = [
        ("Access Control Policy", EvidenceKind.policy,
         ["3.1.1", "3.1.2", "3.1.5", "3.1.6"],
         "# Access Control Policy\n\nUnique accounts, least privilege, quarterly access reviews, "
         "separate administrative accounts, and removal of access on the day of departure.\n"),
        ("Incident Response Plan", EvidenceKind.procedure,
         ["3.6.1", "3.6.2", "3.6.3"],
         "# Incident Response Plan\n\nDetection, triage, containment, DIBNet reporting within 72 hours, "
         "recovery and lessons learned, with the contact tree and an annual tabletop exercise.\n"),
        ("Security Awareness Training Register 2026", EvidenceKind.document,
         ["3.2.1", "3.2.2", "3.2.3"],
         "# Security Awareness Training Register\n\n41 of 41 employees completed CUI handling and "
         "insider-threat awareness training; refresher due annually.\n"),
        ("Network Diagram and Boundary Description", EvidenceKind.document,
         ["3.13.1", "3.13.5", "3.13.6"],
         "# Network Diagram\n\nCUI enclave VLAN 20, shop floor VLAN 90, guest VLAN 30, and the "
         "FortiGate boundary with default-deny inbound.\n"),
        ("Media Protection and Sanitization Procedure", EvidenceKind.procedure,
         ["3.8.1", "3.8.3", "3.8.7"],
         "# Media Protection and Sanitization\n\nMarking, storage, transport, encrypted USB issue and "
         "the NIST SP 800-88 disposal routine with certificates of destruction.\n"),
    ]
    for title, kind, control_ids, body in documents:
        import hashlib

        payload = body.encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        file_name = title.lower().replace(" ", "-") + ".md"
        path = directory / f"{digest[:12]}_{file_name}"
        path.write_bytes(payload)
        evidence = Evidence(
            system_id=system.id,
            title=title,
            kind=kind,
            description=f"{title} approved by the owner and reviewed annually.",
            file_name=file_name,
            file_path=str(path),
            content_type="text/markdown",
            size_bytes=len(payload),
            sha256=digest,
            collected_at=utcnow(),
            expires_at=utcnow() + timedelta(days=365),
            source=EvidenceSource.manual,
        )
        session.add(evidence)
        session.flush()
        for control_id in control_ids:
            session.add(EvidenceLink(evidence_id=evidence.id, control_id=control_id))
            for objective_id in catalog.objective_ids_for(control_id)[:2]:
                session.add(
                    EvidenceLink(
                        evidence_id=evidence.id, control_id=control_id, objective_id=objective_id
                    )
                )
    _ = today
    session.flush()


def _seed_poam(session: Session, system: System) -> None:
    if session.exec(
        select(PoamItem).where(PoamItem.system_id == system.id, PoamItem.source != PoamSource.agent)
    ).first():
        return
    today = date.today()
    items = [
        ("3.5.3", "Roll out multifactor authentication to general users",
         "MFA covers remote access and administrators. General users still sign in to shop-floor "
         "workstations with a password only.", RiskLevel.high, PoamStatus.in_progress, -45, 30,
         ["Purchase 45 FIDO2 security keys", "Pilot with the engineering team",
          "Enrol all users and enforce the conditional access policy"]),
        ("3.13.11", "Record FIPS-validated cryptography and enable FIPS mode",
         "Encryption is in use everywhere but the CMVP certificate numbers are not recorded and "
         "FIPS mode is not enabled on workstations.", RiskLevel.high, PoamStatus.in_progress, -20, 60,
         ["Inventory every cryptographic module protecting CUI",
          "Record CMVP certificate numbers in the SSP appendix",
          "Enable FIPS mode by Group Policy and test the line-of-business applications"]),
        ("3.11.2", "Stand up recurring vulnerability scanning",
         "No authenticated vulnerability scanning is performed; patch reports are the only signal.",
         RiskLevel.high, PoamStatus.open, -15, 45,
         ["Select a scanner with the MSP", "Scan the enclave monthly and on change",
          "Feed findings into the remediation ticket queue"]),
        ("3.12.1", "Perform and document a periodic security assessment",
         "Requirements have never been formally assessed against the 800-171A objectives.",
         RiskLevel.high, PoamStatus.open, -10, 90,
         ["Book the annual self-assessment", "Assess all 320 objectives and record the evidence",
          "Submit the score to SPRS"]),
        ("3.14.6", "Enable monitoring of inbound and outbound traffic",
         "The firewall logs traffic but nobody reviews it and there is no alerting.",
         RiskLevel.high, PoamStatus.open, -60, 30,
         ["Enable IPS in blocking mode", "Forward logs to the MSP's monitoring service",
          "Agree the alert response process and out-of-hours cover in the contract"]),
        ("3.4.8", "Implement application allow-listing",
         "Deny-by-exception software policy is not enforced on workstations.",
         RiskLevel.high, PoamStatus.open, -8, 150,
         ["Inventory software in use", "Pilot Windows Defender Application Control in audit mode",
          "Enforce on the engineering workstations first"]),
        ("3.11.3", "Remediate scan findings against the risk assessment",
         "Without scanning there is no remediation record tied to risk.",
         RiskLevel.moderate, PoamStatus.open, -15, 60,
         ["Define remediation timeframes by severity", "Track findings to closure in the ticket queue"]),
        ("3.3.6", "Provide audit record reduction and reporting",
         "Audit records can be read on each system but cannot be searched or reported on together.",
         RiskLevel.low, PoamStatus.open, -8, 120,
         ["Forward logs to one collector", "Agree the weekly review and who performs it"]),
        ("3.13.16", "Protect CUI at rest on the shop-floor controllers",
         "The CNC controllers cannot run BitLocker; the compensating procedure is not yet written.",
         RiskLevel.moderate, PoamStatus.open, -25, 75,
         ["Confirm with the vendors whether encryption is supported",
          "Write the end-of-job deletion procedure and train the operators"]),
        ("3.8.9", "Verify and test CUI backups",
         "Backups run nightly but restoration had never been tested and the backup copy was not "
         "confirmed encrypted.", RiskLevel.low, PoamStatus.completed, -120, -30,
         ["Confirm backup encryption and key custody", "Perform a documented restore test"]),
    ]
    for (control_id, title, description, risk, status, identified_offset, due_offset,
         milestones) in items:
        item = PoamItem(
            system_id=system.id,
            control_id=control_id,
            title=title,
            weakness_description=description,
            source=PoamSource.self_assessment,
            risk_level=risk,
            status=status,
            owner="Tom Byrne",
            identified_at=today + timedelta(days=identified_offset),
            scheduled_completion=today + timedelta(days=due_offset),
            actual_completion=today + timedelta(days=due_offset) if status == PoamStatus.completed
            else None,
            remediation_plan=milestones[0],
        )
        session.add(item)
        session.flush()
        for position, text in enumerate(milestones):
            session.add(
                PoamMilestone(
                    poam_item_id=item.id,
                    description=text,
                    due_date=today + timedelta(days=due_offset - (len(milestones) - position - 1) * 10),
                    completed_at=utcnow() if status == PoamStatus.completed else None,
                    position=position,
                )
            )
    session.flush()


def _agent_payloads() -> list[dict]:
    """Two endpoints: a well-managed CAD workstation and a neglected CNC controller."""
    from .schemas import AgentReportIn

    now = utcnow()
    good = {
        "schema_version": 1,
        "agent": {"name": "bulwark-agent", "version": "0.1.0", "platform": "windows"},
        "asset": {
            "hostname": "ENG-CAD-01",
            "fqdn": "eng-cad-01.precision.local",
            "os_family": "windows",
            "os_name": "Windows 11 Pro",
            "os_version": "10.0.22631",
            "arch": "x86_64",
            "domain": "PRECISION",
            "serial_number": "5CG3210ABC",
            "ip_addresses": ["10.20.1.21"],
            "mac_addresses": ["00:1a:2b:3c:4d:5e"],
            "logged_in_users": ["PRECISION\\malvarez"],
        },
        "collected_at": now.isoformat(),
        "checks": [
            {"check_id": "os.firewall.enabled", "status": "pass",
             "observed": "Domain: On; Private: On; Public: On"},
            {"check_id": "os.firewall.default_inbound_block", "status": "pass",
             "observed": "All profiles: Block"},
            {"check_id": "os.disk.encryption", "status": "pass",
             "observed": "C: FullyEncrypted (BitLocker, XtsAes256)"},
            {"check_id": "os.malware.protection_enabled", "status": "pass",
             "observed": "Defender real-time protection enabled, tamper protection on"},
            {"check_id": "os.malware.signatures_current", "status": "pass",
             "observed": "Signatures 0 days old"},
            {"check_id": "os.malware.last_scan", "status": "pass", "observed": "Quick scan 2 days ago"},
            {"check_id": "os.patch.last_update", "status": "pass",
             "observed": "KB5041585 installed 6 days ago"},
            {"check_id": "os.patch.pending_updates", "status": "pass", "observed": "0 pending updates"},
            {"check_id": "os.patch.auto_update", "status": "pass",
             "observed": "AUOptions=4 (managed by RMM)"},
            {"check_id": "os.patch.os_supported", "status": "pass", "observed": "Windows 11 23H2 supported"},
            {"check_id": "os.session.screen_lock", "status": "pass",
             "observed": "Lock after 600 s, password required"},
            {"check_id": "os.session.logon_banner", "status": "pass", "observed": "Legal notice configured"},
            {"check_id": "os.session.idle_timeout", "status": "pass", "observed": "RDP MaxIdleTime 1800 s"},
            {"check_id": "os.password.min_length", "status": "pass", "observed": "Minimum length 14"},
            {"check_id": "os.password.complexity", "status": "pass", "observed": "Complexity enabled"},
            {"check_id": "os.password.history", "status": "pass", "observed": "History 24 passwords"},
            {"check_id": "os.lockout.threshold", "status": "pass", "observed": "Lockout after 5 attempts"},
            {"check_id": "os.accounts.admin_count", "status": "pass",
             "observed": "1 enabled local administrator"},
            {"check_id": "os.accounts.guest_disabled", "status": "pass", "observed": "Guest disabled"},
            {"check_id": "os.accounts.autologon_disabled", "status": "pass", "observed": "AutoAdminLogon=0"},
            {"check_id": "os.accounts.uac_enabled", "status": "pass",
             "observed": "EnableLUA=1, ConsentPromptBehaviorAdmin=2"},
            {"check_id": "os.audit.logging_enabled", "status": "pass",
             "observed": "Logon, Account Management and Policy Change auditing: Success and Failure"},
            {"check_id": "os.audit.log_retention", "status": "pass", "observed": "Security log 512 MB"},
            {"check_id": "os.audit.privileged_actions", "status": "pass",
             "observed": "Sensitive Privilege Use and Process Creation auditing on"},
            {"check_id": "os.audit.powershell_logging", "status": "pass",
             "observed": "EnableScriptBlockLogging=1"},
            {"check_id": "os.time.sync", "status": "pass",
             "observed": "Synchronised with the domain 2 h ago"},
            {"check_id": "os.crypto.fips_mode", "status": "fail",
             "observed": "FipsAlgorithmPolicy Enabled=0"},
            {"check_id": "os.crypto.legacy_tls_disabled", "status": "pass",
             "observed": "SSL 2.0/3.0 and TLS 1.0/1.1 disabled"},
            {"check_id": "os.crypto.smb_signing", "status": "pass", "observed": "RequireSecuritySignature=1"},
            {"check_id": "os.services.legacy_protocols", "status": "pass",
             "observed": "SMB1, Telnet and TFTP not installed"},
            {"check_id": "os.media.usb_storage_blocked", "status": "pass",
             "observed": "USBSTOR Start=4 (blocked by policy)"},
            {"check_id": "os.media.autorun_disabled", "status": "pass", "observed": "NoDriveTypeAutoRun=255"},
            {"check_id": "os.remote.remote_access", "status": "pass",
             "observed": "RDP enabled with NLA required (UserAuthentication=1)"},
            {"check_id": "os.platform.secure_boot", "status": "pass", "observed": "Secure Boot enabled"},
        ],
        "inventory": {
            "local_users": [{"name": "malvarez", "enabled": True, "admin": False},
                            {"name": "localadmin", "enabled": True, "admin": True}],
            "software": [{"name": "SolidWorks", "version": "2026 SP2", "publisher": "Dassault"},
                         {"name": "Microsoft 365 Apps", "version": "16.0", "publisher": "Microsoft"}],
            "listening_ports": [{"proto": "tcp", "port": 3389, "process": "svchost"}],
            "services": [{"name": "WinDefend", "state": "running"}],
        },
    }
    bad = {
        "schema_version": 1,
        "agent": {"name": "bulwark-agent", "version": "0.1.0", "platform": "windows"},
        "asset": {
            "hostname": "SHOP-CNC-01",
            "fqdn": "shop-cnc-01.precision.local",
            "os_family": "windows",
            "os_name": "Windows 10 IoT Enterprise LTSC",
            "os_version": "10.0.19044",
            "arch": "x86_64",
            "domain": None,
            "serial_number": "HAAS-99213",
            "ip_addresses": ["10.20.9.11"],
            "mac_addresses": ["00:aa:bb:cc:dd:ee"],
            "logged_in_users": ["operator"],
        },
        "collected_at": now.isoformat(),
        "checks": [
            {"check_id": "os.firewall.enabled", "status": "fail",
             "observed": "Domain: On; Private: Off; Public: Off"},
            {"check_id": "os.firewall.default_inbound_block", "status": "fail",
             "observed": "Private profile default inbound: Allow"},
            {"check_id": "os.disk.encryption", "status": "fail",
             "observed": "C: FullyDecrypted (BitLocker not enabled)"},
            {"check_id": "os.malware.protection_enabled", "status": "fail",
             "observed": "Defender real-time protection disabled by local policy"},
            {"check_id": "os.malware.signatures_current", "status": "fail",
             "observed": "Signatures 94 days old"},
            {"check_id": "os.malware.last_scan", "status": "fail", "observed": "No scan recorded"},
            {"check_id": "os.patch.last_update", "status": "fail",
             "observed": "Most recent hotfix installed 412 days ago"},
            {"check_id": "os.patch.auto_update", "status": "fail", "observed": "NoAutoUpdate=1"},
            {"check_id": "os.patch.os_supported", "status": "pass",
             "observed": "Windows 10 IoT Enterprise LTSC 2021: supported until 2032-01-13"},
            {"check_id": "os.session.screen_lock", "status": "fail",
             "observed": "Screen saver not secure; no inactivity lock configured"},
            {"check_id": "os.session.logon_banner", "status": "fail",
             "observed": "No legal notice configured"},
            {"check_id": "os.password.min_length", "status": "fail", "observed": "Minimum length 0"},
            {"check_id": "os.password.complexity", "status": "fail", "observed": "Complexity disabled"},
            {"check_id": "os.lockout.threshold", "status": "fail", "observed": "Lockout threshold 0 (never)"},
            {"check_id": "os.accounts.admin_count", "status": "fail",
             "observed": "3 enabled local administrators (operator, setup, admin)"},
            {"check_id": "os.accounts.guest_disabled", "status": "pass", "observed": "Guest disabled"},
            {"check_id": "os.accounts.autologon_disabled", "status": "fail",
             "observed": "AutoAdminLogon=1 with a stored DefaultPassword"},
            {"check_id": "os.audit.logging_enabled", "status": "fail",
             "observed": "Logon auditing: No Auditing"},
            {"check_id": "os.time.sync", "status": "fail",
             "observed": "Last successful sync: unavailable (w32time not running)"},
            {"check_id": "os.crypto.fips_mode", "status": "fail",
             "observed": "FipsAlgorithmPolicy Enabled=0"},
            {"check_id": "os.media.usb_storage_blocked", "status": "fail",
             "observed": "USBSTOR Start=3 (removable storage permitted)"},
            {"check_id": "os.services.legacy_protocols", "status": "fail",
             "observed": "SMB1Protocol enabled"},
            {"check_id": "os.remote.remote_access", "status": "fail",
             "observed": "RDP enabled without Network Level Authentication"},
            {"check_id": "os.platform.secure_boot", "status": "error",
             "observed": "", "error": "Confirm-SecureBootUEFI failed: not a UEFI system"},
        ],
        "inventory": {
            "local_users": [{"name": "operator", "enabled": True, "admin": True},
                            {"name": "setup", "enabled": True, "admin": True}],
            "software": [{"name": "Haas Control Software", "version": "100.22", "publisher": "Haas"}],
            "listening_ports": [{"proto": "tcp", "port": 445, "process": "System"},
                                {"proto": "tcp", "port": 3389, "process": "svchost"}],
            "services": [{"name": "W32Time", "state": "stopped"}],
        },
    }
    return [AgentReportIn.model_validate(good), AgentReportIn.model_validate(bad)]


def seed_demo(session: Session, *, actor: str = "seed") -> dict[str, int | str]:
    """Create the demo organization, system and history. Safe to call repeatedly."""
    org, created_org = _get_or_create_org(session)
    system = session.exec(
        select(System).where(System.organization_id == org.id, System.name == DEMO_SYSTEM)
    ).first()
    created_system = False
    if system is None:
        system = System(
            organization_id=org.id,
            name=DEMO_SYSTEM,
            description="The people, endpoints, servers and cloud services that handle CUI drawings "
            "and specifications received from prime contractors.",
            environment=Environment.hybrid,
            boundary_description="VLAN 20 (engineering and front office), the file server, the "
            "Microsoft 365 GCC High tenant, and the FortiGate that separates them from the shop-floor "
            "machine VLAN, the guest wireless and the internet. The two CNC controllers are "
            "specialized assets on an isolated VLAN reached only through a jump path from VLAN 20.",
            cui_types="CTI (Controlled Technical Information): drawings, specifications, "
            "process sheets and inspection reports received under DFARS 252.204-7012.",
            cui_description="CUI arrives by email and through the customers' portals, is stored in "
            "the GCC High tenant and on the file server, and is used to produce programs for the CNC "
            "machines. Printed travellers carrying CTI are controlled in the shop and shredded.",
            data_flow_description="Prime contractor portal or GCC High email -> SharePoint job "
            "library -> engineering workstation (CAD/CAM) -> program file on the file server -> "
            "CNC controller on the isolated VLAN. Inspection reports return by the same path.",
            status=SystemStatus.active,
        )
        session.add(system)
        session.flush()
        created_system = True

    seed_implementations(session, system)
    _seed_providers(session, org)
    _seed_assets(session, system)
    _apply_statuses(session, system)
    _seed_evidence(session, system)
    _seed_poam(session, system)
    session.flush()

    reports = 0
    for payload in _agent_payloads():
        ingest_report(session, system, payload, actor=actor)
        reports += 1

    log_activity(
        session,
        actor,
        "seed",
        "system",
        system.id,
        f"Seeded demo data for {DEMO_ORG} ({DEMO_SYSTEM})",
        system_id=system.id,
    )
    session.commit()
    return {
        "organization_id": org.id,
        "system_id": system.id,
        "created_organization": int(created_org),
        "created_system": int(created_system),
        "agent_reports": reports,
        "message": f"Demo data ready for {DEMO_ORG} / {DEMO_SYSTEM}",
    }
