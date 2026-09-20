# Shared responsibility and inheritance

Almost every small supplier outsources part of its security: a managed service provider runs the
endpoints, a cloud tenant holds the CUI. That changes who *performs* each requirement. It does not
change who is *accountable* for it.

## The three questions an assessor asks

1. **Who does this?** You, the provider, or both.
2. **How do you know?** A contract clause, a responsibility matrix, a FedRAMP package. Not a phone
   call.
3. **What do you have that proves it happened?** A report, a console export, a ticket.

Bulwark records the first two on the provider's matrix and the third in the evidence library.

## The responsibility field

Each requirement carries a responsibility:

| Value | Meaning |
|---|---|
| **Customer** | You implement it, you evidence it. |
| **Shared** | The provider operates a mechanism, you configure it, set policy and review output. |
| **Provider** | The provider performs it under contract. You still verify and retain the evidence. |
| **Inherited** | Covered inside a provider's authorization boundary and inheritable as-is. |

Mark a requirement **inherited** only when the provider's authorization genuinely covers your CUI:
a FedRAMP Moderate (or higher) authorization for a cloud service, at the impact level your CUI
requires. A managed service provider is not FedRAMP-authorized, so nothing is inherited from one,
no matter how much work they do for you.

Bulwark flags, in the readiness view, any requirement handed to a provider with no provider set or
no matrix row behind it. That gap is exactly what an assessor finds.

## Starting templates

Three templates are included, each covering all 110 requirements:

- **Generic managed service provider** — the usual split when an outsourced IT provider runs
  endpoints, patching, backups, the firewall and the helpdesk. Nothing inherited.
- **Generic FedRAMP Moderate cloud service** — physical, environmental, maintenance and
  infrastructure with the provider; identity, data handling, training and incident coordination
  with you or shared.
- **Microsoft 365 GCC High (starter)** — a realistic split for a shop whose CUI lives in a GCC High
  tenant with endpoints managed by Intune.

Apply one from the provider page, then **reconcile it against the provider's own documentation**.
A template is a starting point that saves you typing 110 rows. It is not evidence, and the
disclaimer on each one says so.

## The MSP is in scope too

If your provider handles CUI, or provides a security function for the CUI environment, their own
systems are in scope. Their remote monitoring agent is a security protection asset in your
inventory. Under CMMC they may need their own assessment. Ask them where they stand and record the
answer; it is a question a prime contractor will ask you.
