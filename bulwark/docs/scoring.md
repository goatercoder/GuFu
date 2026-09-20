# How the score works

Bulwark implements the *NIST SP 800-171 DoD Assessment Methodology, Version 1.2.1* as carried into
**32 CFR § 170.24** (CMMC scoring), and the plan-of-action rules of **32 CFR § 170.21**.

## The arithmetic

You start at **110** and subtract a point value for every requirement that is not met.

| Point value | Requirements | What it means |
|---|---|---|
| 5 | 44 | Absence has a specific and confined effect on the security of the system |
| 3 | 14 | Absence has a specific and limited effect |
| 1 | 51 | Absence has a limited or indirect effect |
| 0 | 1 | Requirement 3.12.4 only; see below |

That totals 313 points of possible deduction, so the **minimum possible score is −203**. A negative
score is normal for a company that has not started: it is not an error.

A requirement counts as met when its status is **implemented** or **not applicable**. Everything
else — partially implemented, planned, not implemented — deducts the full value.

## Partial credit

Two requirements deduct 3 instead of 5 when a specific partial state is true.

**3.5.3 Multifactor Authentication.** Multifactor is implemented for remote access and privileged
accounts, but not for general (non-privileged local) users.

**3.13.11 FIPS-validated cryptography.** Encryption is employed to protect CUI, but the modules are
not FIPS-validated.

Set these with the *Partial credit* field on the requirement. Nothing else carries partial credit:
a requirement is either met or it is not.

## The system security plan

Requirement **3.12.4** asks for a system security plan. It has **no point value**, because without
a plan there is nothing to assess. Bulwark deducts nothing for it but marks the assessment
*blocked*, which also blocks conditional eligibility. Generate the plan from **Documents**, fill in
the boundary and your narratives, then mark 3.12.4 implemented.

## Conditional certification eligibility

A Conditional CMMC Status lets you operate while a small number of gaps sit on a plan of action.
Under 32 CFR § 170.21(a)(2) it requires **all** of:

1. A score of at least **88** (80 % of 110).
2. Every remaining unmet requirement worth **1 point**. The single exception is 3.13.11 at partial
   credit, which may remain at its 3-point deduction.
3. **None** of these five outstanding, which may never sit on a plan of action:
   `3.1.20`, `3.1.22`, `3.10.3`, `3.10.4`, `3.10.5`.
4. A system security plan in place (see above).

The dashboard states which of these is failing, by name. Items on a plan of action must be closed
within **180 days**; Bulwark warns as an item approaches and passes that age.

## Objectives override claims

NIST SP 800-171A breaks the 110 requirements into **320 assessment objectives**. An assessor tests
the objectives, not your summary of them. So if a requirement is recorded as implemented while one
of its objectives is recorded as *not met*, Bulwark scores it as partially implemented and raises a
consistency warning. Fix one or the other; do not leave them disagreeing on the day of the
assessment.

The same principle drives the **contradiction** panel on the dashboard: a requirement recorded as
met, with an automated check failing on an in-scope asset right now, is a finding waiting to
happen.

## A worked example

The demo machine shop scores **80**. It has met 100 of 110 requirements, three of which are
justified as not applicable. Its deductions:

| Requirement | Status | Deducted |
|---|---|---|
| 3.3.6 Audit record reduction | Not implemented | 1 |
| 3.4.8 Application execution policy | Not implemented | 5 |
| 3.5.3 Multifactor authentication | Partial (remote and privileged only) | 3 |
| 3.6.3 Incident response testing | Planned | 1 |
| 3.11.2 Vulnerability scanning | Not implemented | 5 |
| 3.11.3 Vulnerability remediation | Not implemented | 1 |
| 3.12.1 Security control assessment | Not implemented | 5 |
| 3.13.11 FIPS cryptography | Partial (not FIPS-validated) | 3 |
| 3.13.16 Data at rest | Planned | 1 |
| 3.14.6 Monitor communications | Not implemented | 5 |

110 − 30 = **80**. Eight short of the 88 needed for a conditional status, and blocked besides by
four 5-point gaps and one 3-point gap. Closing the four 5-point requirements alone takes the score
to 100 and leaves only 3.5.3 blocking eligibility.

## Submitting to SPRS

Bulwark computes the score; it does not submit it. You enter it in the Supplier Performance Risk
System yourself, along with the assessment date and the date you expect to meet all requirements.
The score you submit is an assertion you are accountable for under DFARS 252.204-7020. Export the
readiness report from **Documents** to have the evidence behind the number.
