# Bulwark

**CMMC Level 2 compliance automation for small defense suppliers.**

If your company touches Controlled Unclassified Information, you have to implement 110 security
requirements from NIST SP 800-171 Rev 2 and prove it to an assessor. Most of the companies in that
position are 40-person machine shops with one IT person. Consultants charge $15,000 to $80,000 to
walk them through it, largely to produce documents and chase evidence.

Bulwark does the mechanical parts: it tells you where you stand, writes the documents, tracks what
is left, and collects evidence from your actual computers every day instead of once a year.

---

## What it does

**Tells you what you still have to do.** Every requirement scored the way the Department of Defense
scores it: 110 points, minus 5, 3 or 1 for each one you have not met, down to a floor of −203. The
dashboard shows the score, whether you qualify for a Conditional CMMC Status, exactly what is
blocking it, and the ranked list of gaps worth the most points.

**Writes the required documents.** A complete System Security Plan in Word, HTML, Markdown or JSON,
covering all 110 requirements with your narrative, the SP 800-171A assessment objectives, your
evidence and your open items. Plus a POA&M export in the columns assessors expect, and a short
readiness briefing for the owner. Requirement 3.12.4 asks for a system security plan; this is it.

**Tracks the problems you have to fix.** A plan of action with owners, dates, milestones and a
status workflow, warnings when an item goes overdue or passes the 180-day limit, and automatic
items raised from failing endpoint checks.

**Checks your computers for proof.** A dependency-free agent on each Windows, Linux or macOS
machine reads 33 to 40 configuration settings a day (firewall, disk encryption, patching,
anti-malware, audit policy, password policy, screen lock, USB, FIPS mode and more) and the server
maps each result to the requirements and assessment objectives it evidences.

**Shows you how ready you really are.** Beyond the score: evidence coverage per objective,
automated coverage per requirement, stale evidence, overdue items, and the signal nobody else
gives you — **requirements you have recorded as met that a live endpoint check disproves.** An
assessor tests the objective, not the claim.

---

## Five-minute start

```bash
git clone <this repository>
cd bulwark
./start.sh                 # macOS and Linux
start.bat                  # Windows
```

Open <http://127.0.0.1:8800>. The password is printed on first start and saved to
`backend/data/admin_password.txt`; set `BULWARK_ADMIN_PASSWORD` to choose your own.

Want to see it populated first? Sign in, open **Settings → Load demo data**, and you get a
41-person machine shop part-way through readiness: twelve assets across every CMMC category, an
MSP and a Microsoft 365 GCC High tenant with responsibility matrices, an open plan of action, and
two endpoints reporting, one of them badly configured.

With Docker:

```bash
docker compose up --build       # http://127.0.0.1:8800, data in a named volume
```

## Putting agents on your machines

Open **Agents**, copy the command for the platform, and run it once, elevated, on each machine:

```powershell
powershell -ExecutionPolicy Bypass -File .\Bulwark-Agent.ps1 `
    -Server https://bulwark.example -Key <enrollment key> -InstallScheduledTask
```

```bash
sudo python3 bulwark_agent.py --server https://bulwark.example --key <key> --install-schedule
```

It installs a daily task, reads configuration, and reports. It never changes a setting. A machine
with no route to the server can write a file with `--output` and you upload it by hand. See
[agent/README.md](agent/README.md).

## How the score works

Scoring follows the *NIST SP 800-171 DoD Assessment Methodology* as carried into 32 CFR § 170.24:
start at 110, subtract each unmet requirement's point value. Two requirements carry partial credit
(multifactor authentication and FIPS-validated cryptography deduct 3 instead of 5). Requirement
3.12.4 deducts nothing but stops an assessment from being completed at all.

Conditional certification eligibility follows 32 CFR § 170.21: at least 88 points, every remaining
gap worth 1 point (FIPS cryptography at partial credit is the single exception), and none of the
five requirements that may never sit on a plan of action.

Full detail, with a worked example, in [docs/scoring.md](docs/scoring.md).

## How it is built

| | |
|---|---|
| Backend | Python 3.11, FastAPI, SQLModel, SQLite. One process, one file of data. |
| Frontend | React 19, TypeScript, Vite. Built to static files the backend serves. |
| Agents | One Python file (3.8+, standard library only), one PowerShell file (5.1+). |
| Catalog | `catalog/cmmc_l2_catalog.json`, built from its sources by `catalog/build_catalog.py`. |
| Tests | 139 backend, 51 agent. `make test`. |

```
bulwark/
  catalog/     the 110 requirements, 320 assessment objectives, 42 automated checks
  backend/     the API, the scoring engine, the document generators
  agent/       the endpoint collectors
  frontend/    the web interface
  docs/        scoping, scoring, shared responsibility, deployment
```

`ARCHITECTURE.md` is the contract the code is written against: data model, API, scoring rules,
agent report schema.

## Security

- One administrator password, stored hashed nowhere else and never logged.
- Each system has an enrollment key that lets agents report in. It is not an administrative
  credential: it cannot read or change anything, and you can rotate it at any time.
- All data stays on your machine, in SQLite and a directory of evidence files. Nothing is sent
  anywhere.
- Bulwark binds to 127.0.0.1 by default. If you expose it, put it behind a reverse proxy with TLS.
- Back up `backend/data/`. It is your compliance record.

See [docs/deployment.md](docs/deployment.md).

## Where the content comes from

The requirement statements, discussion text and the SP 800-171A assessment objectives are works of
the United States Government and are in the public domain. They are loaded here from a schema-valid
OSCAL catalog; see [catalog/sources/ATTRIBUTION.md](catalog/sources/ATTRIBUTION.md) for the full
citation and licence. Point values follow the DoD Assessment Methodology v1.2.1 and 32 CFR § 170.24;
plan-of-action rules follow 32 CFR § 170.21. The plain-language guidance on each requirement was
written for this project.

## What this is not

Bulwark supports an assessment; it does not replace one. A CMMC Level 2 certification requires an
assessment by a certified third-party assessment organization, and a self-assessment score you
submit to SPRS is an assertion you are accountable for. Use Bulwark to know what is true about your
systems and to have the documents ready. Do not use it as a substitute for reading the standard or
for professional advice about your particular contracts.
