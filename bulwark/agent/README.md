# Bulwark evidence-collection agents

These scripts read configuration state from an endpoint and send it to your Bulwark server, which
maps each result to the NIST SP 800-171 requirements and SP 800-171A assessment objectives it
supports. Instead of taking a screenshot once a year, every machine proves its own configuration
every day.

**They read; they never change anything.** No registry writes, no policy edits, no installs beyond
the optional scheduled task you ask for.

| | |
|---|---|
| Windows | `Bulwark-Agent.ps1` (Windows PowerShell 5.1+, no modules to install) |
| Linux, macOS | `bulwark_agent.py` (Python 3.8+, standard library only) |
| Data sent | check results, plus a hardware/software/account inventory |
| Data never sent | file contents, documents, drawings, passwords or key material |

## What it collects

40 checks on Windows, 33 on Linux and 34 on macOS, covering:

- **Accounts and access**: administrator count, guest account, blank passwords, inactive accounts,
  automatic logon, User Account Control.
- **Authentication policy**: minimum password length, complexity, history, account lockout.
- **Sessions**: screen lock with a password, logon banner, idle session termination.
- **Network**: host firewall state and default inbound action, remote access hardening, legacy
  protocols (SMBv1, Telnet, FTP, TFTP), time synchronization.
- **Audit**: audit policy coverage, log size and retention, privileged action auditing, PowerShell
  script block logging.
- **Endpoint protection and patching**: anti-malware presence and real-time protection, signature
  age, last scan, last update, pending updates, automatic updates, vendor support status.
- **Cryptography and media**: disk encryption, FIPS mode, legacy TLS, SMB signing, USB mass storage,
  AutoRun, Secure Boot, Gatekeeper and System Integrity Protection on macOS.
- **Inventory**: hostname and operating system, installed software, local accounts, listening ports,
  services.

Run `--list-checks` (or `-ListChecks`) to print the exact set for a platform. The authoritative
definitions, including which requirement each check evidences, live in `catalog/checks.json`.

## Install

Open **Agents** in Bulwark and copy the command for the platform. It already contains your server
URL and the system's enrollment key.

### Windows

Run once, elevated, to install a daily task that runs as SYSTEM:

```powershell
powershell -ExecutionPolicy Bypass -File .\Bulwark-Agent.ps1 `
    -Server https://bulwark.example -Key <enrollment key> -InstallScheduledTask
```

The server URL and key are stored in `%ProgramData%\Bulwark\agent.json`, restricted to SYSTEM and
the administrators group. Remove the task with `-UninstallScheduledTask`.

Run it elevated. Without administrative rights the audit policy, password policy and BitLocker
probes report an error explaining why rather than a misleading pass or fail.

### Linux and macOS

```bash
sudo python3 bulwark_agent.py --server https://bulwark.example --key <enrollment key> \
    --install-schedule
```

That writes `/etc/bulwark/agent.json` (mode 600) and installs a daily run at a host-derived minute
after 03:00, so a fleet does not report in lockstep: `/etc/cron.d/bulwark-agent` on Linux, a launch
daemon at `/Library/LaunchDaemons/com.bulwark.agent.plist` on macOS. Remove it with
`--uninstall-schedule`.

Run it with `sudo`. Without root, `/etc/shadow` and some policy files cannot be read and those
checks report the reason.

## Offline machines

A machine with no route to the server still produces evidence:

```bash
python3 bulwark_agent.py --output report.json
```

```powershell
.\Bulwark-Agent.ps1 -Output report.json
```

Copy the file to a machine that can reach Bulwark and upload it on the **Agents** page, or:

```bash
curl -X POST -H "Authorization: Bearer <enrollment key>" \
     -H "Content-Type: application/json" --data @report.json \
     https://bulwark.example/api/agents/report
```

## Troubleshooting

```bash
python3 bulwark_agent.py --dry-run                      # print the report, send nothing
python3 bulwark_agent.py --check os.firewall.enabled    # run one check
python3 bulwark_agent.py --list-checks                  # what runs on this platform
python3 bulwark_agent.py --verbose --dry-run            # log each check as it runs
```

```powershell
.\Bulwark-Agent.ps1 -DryRun
.\Bulwark-Agent.ps1 -Check os.firewall.enabled
.\Bulwark-Agent.ps1 -ListChecks
```

Exit codes: `0` success, `2` the report could not be delivered, `3` bad arguments or no
configuration.

A check reports `error` when it could not determine the answer, which is different from `fail`.
Read the message: it usually says the agent needs elevation or that a tool is missing.

## Security notes

- The enrollment key authorizes reporting into one system only. It is not an administrative
  credential and cannot read or change anything in Bulwark.
- Rotate it on the Agents page if it is exposed. Agents must then be reconfigured.
- The key is never written to the console, to logs or into the scheduled task command line.
- Use HTTPS. `--insecure` / `-Insecure` skips certificate verification and prints a warning; use it
  only against a server with a self-signed certificate on a trusted network.
- Every report is recorded with the time it was collected and received, so stale agents are visible
  rather than silently counting as evidence.
