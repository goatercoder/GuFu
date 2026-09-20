#!/usr/bin/env python3
"""Bulwark evidence-collection agent for Linux, macOS and Windows.

Collects configuration state that supports NIST SP 800-171 Rev 2 requirements and posts it to a
Bulwark server, which maps each check to the requirements and assessment objectives it evidences.

Standard library only, Python 3.8+. It reads configuration; it never changes it.

    python3 bulwark_agent.py --server https://bulwark.example --key <enrollment key>
    python3 bulwark_agent.py --output report.json      # offline: write, carry, upload
    python3 bulwark_agent.py --dry-run                 # print what would be sent
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime

__version__ = "0.1.0"

SCHEMA_VERSION = 1

#: Thresholds, mirroring catalog/checks.json "params".
PARAMS = {
    "os.accounts.admin_count": {"max_admins": 2},
    "os.accounts.inactive_enabled": {"inactive_days": 90},
    "os.password.min_length": {"min_length": 14},
    "os.password.history": {"history": 5},
    "os.lockout.threshold": {"max_threshold": 10},
    "os.session.screen_lock": {"max_seconds": 900},
    "os.session.idle_timeout": {"max_seconds": 3600},
    "os.time.sync": {"max_hours": 24},
    "os.audit.log_retention": {"min_mb": 196},
    "os.malware.signatures_current": {"max_days": 7},
    "os.malware.last_scan": {"max_days": 7},
    "os.patch.last_update": {"max_days": 30},
}

CONFIG_PATHS = [
    "/etc/bulwark/agent.json",
    os.path.expanduser("~/.config/bulwark/agent.json"),
    os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "Bulwark", "agent.json"),
]

PASS, FAIL, ERROR, NA, INFO = "pass", "fail", "error", "not_applicable", "info"

_registry = []


def check(check_id, platforms):
    """Register a check function for the given platforms ('windows', 'linux', 'macos')."""

    def decorator(func):
        _registry.append({"id": check_id, "platforms": tuple(platforms), "func": func})
        return func

    return decorator


def param(check_id, name):
    return PARAMS.get(check_id, {}).get(name)


# --------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------
def current_platform():
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    return "linux"


PLATFORM = current_platform()


def run(command, timeout=25, shell=False):
    """Run a command and return (returncode, stdout, stderr); never raises."""
    try:
        completed = subprocess.run(
            command,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return (
            completed.returncode,
            completed.stdout.decode("utf-8", "replace"),
            completed.stderr.decode("utf-8", "replace"),
        )
    except FileNotFoundError:
        return 127, "", "command not found"
    except subprocess.TimeoutExpired:
        return 124, "", "timed out"
    except OSError as exc:  # permissions, exec format, ...
        return 126, "", str(exc)


def powershell(script, timeout=45):
    """Run a PowerShell snippet on Windows and return its stdout."""
    code, out, err = run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", script],
        timeout=timeout,
    )
    return code, out.strip(), err.strip()


def read_text(path, limit=200000):
    try:
        with open(path, "r", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return None


def which(name):
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def utcnow_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def result(status, observed, expected=None, details=None, error=None):
    return {"status": status, "observed": observed, "expected": expected,
            "details": details, "error": error}


def needs_root(message="run the agent with sudo or as root to read this setting"):
    return result(ERROR, "", error=message)


def parse_key_values(text, separator="="):
    """Parse simple 'key=value' or 'key: value' output into a dict (lower-cased keys)."""
    values = {}
    for line in (text or "").splitlines():
        if separator in line:
            key, _, value = line.partition(separator)
            values[key.strip().lower()] = value.strip()
    return values


def secedit_export():
    """Windows local security policy as a dict, via secedit (falls back to net accounts)."""
    if PLATFORM != "windows":
        return {}
    temp = os.path.join(os.environ.get("TEMP", r"C:\Windows\Temp"), "bulwark_secpol.inf")
    code, _, _ = run(["secedit", "/export", "/cfg", temp, "/quiet"], timeout=45)
    if code != 0:
        return {}
    try:
        with open(temp, "r", encoding="utf-16", errors="replace") as handle:
            text = handle.read()
    except (OSError, UnicodeError):
        text = read_text(temp) or ""
    finally:
        try:
            os.remove(temp)
        except OSError:
            pass
    return parse_key_values(text)


_SECPOL_CACHE = {}


def secpol(key, default=None):
    if not _SECPOL_CACHE:
        _SECPOL_CACHE.update(secedit_export() or {"_loaded": "1"})
    value = _SECPOL_CACHE.get(key.lower())
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def reg_query(path, name):
    """Read one Windows registry value; returns a string or None."""
    if PLATFORM != "windows":
        return None
    code, out, _ = run(["reg", "query", path, "/v", name], timeout=20)
    if code != 0:
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0].lower() == name.lower():
            return " ".join(parts[2:]).strip()
    return None


def reg_int(path, name):
    raw = reg_query(path, name)
    if raw is None:
        return None
    try:
        return int(raw, 16) if raw.lower().startswith("0x") else int(raw)
    except ValueError:
        return None


def sshd_config():
    """Effective sshd settings via 'sshd -T', falling back to parsing sshd_config."""
    for candidate in ("/usr/sbin/sshd", "/usr/local/sbin/sshd", which("sshd")):
        if candidate and os.path.exists(candidate):
            code, out, _ = run([candidate, "-T"], timeout=20)
            if code == 0 and out:
                values = {}
                for line in out.splitlines():
                    key, _, value = line.partition(" ")
                    values.setdefault(key.strip().lower(), value.strip())
                return values
    text = read_text("/etc/ssh/sshd_config")
    if not text:
        return {}
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition(" ")
        values.setdefault(key.strip().lower(), value.strip())
    return values


def macos_defaults(domain, key, host=False):
    command = ["defaults"]
    if host:
        command.append("-currentHost")
    command += ["read", domain, key]
    code, out, _ = run(command, timeout=15)
    return out.strip() if code == 0 else None


def days_since(timestamp):
    return (datetime.utcnow() - timestamp).days


# --------------------------------------------------------------------------------------------
# Inventory checks
# --------------------------------------------------------------------------------------------
@check("os.inventory.system", ["windows", "linux", "macos"])
def check_system_inventory():
    details = {
        "hostname": socket.gethostname(),
        "platform": PLATFORM,
        "os_name": os_name(),
        "os_version": platform.release(),
        "arch": platform.machine(),
        "python": platform.python_version(),
    }
    return result(INFO, "{0} on {1} ({2})".format(details["os_name"], details["hostname"],
                                                  details["arch"]), details=details)


@check("os.inventory.software", ["windows", "linux", "macos"])
def check_software_inventory():
    software = installed_software()
    return result(INFO, "{0} installed package(s) recorded".format(len(software)),
                  details={"software": software[:500]})


@check("os.inventory.local_users", ["windows", "linux", "macos"])
def check_local_users():
    users = local_users()
    if users is None:
        return needs_root("cannot enumerate local accounts")
    admins = [u["name"] for u in users if u.get("admin") and u.get("enabled", True)]
    disabled_admins = [u["name"] for u in users if u.get("admin") and not u.get("enabled", True)]
    enabled = [u for u in users if u.get("enabled", True)]
    return result(
        INFO,
        "{0} local account(s), {1} enabled; {2} enabled administrator(s)".format(
            len(users), len(enabled), len(admins)),
        details={"users": users, "administrators": admins,
                 "disabled_administrators": disabled_admins},
    )


@check("os.inventory.listening_ports", ["windows", "linux", "macos"])
def check_listening_ports():
    ports = listening_ports()
    if ports is None:
        return result(ERROR, "", error="no supported tool found (ss, netstat or lsof)")
    summary = ", ".join(sorted({str(p["port"]) for p in ports})[:12])
    return result(INFO, "{0} listening socket(s): {1}".format(len(ports), summary or "none"),
                  details={"listening_ports": ports})


# --------------------------------------------------------------------------------------------
# Account checks
# --------------------------------------------------------------------------------------------
@check("os.accounts.admin_count", ["windows", "linux", "macos"])
def check_admin_count():
    maximum = param("os.accounts.admin_count", "max_admins")
    users = local_users()
    if users is None:
        return needs_root("cannot enumerate local administrators")
    admins = sorted(u["name"] for u in users if u.get("admin") and u.get("enabled", True))
    status = PASS if len(admins) <= maximum else FAIL
    return result(
        status,
        "{0} enabled local administrator(s): {1}".format(len(admins), ", ".join(admins) or "none"),
        expected="At most {0} enabled local administrator accounts".format(maximum),
        details={"administrators": admins},
    )


@check("os.accounts.guest_disabled", ["windows", "macos"])
def check_guest_disabled():
    if PLATFORM == "windows":
        code, out, _ = run(["net", "user", "Guest"], timeout=20)
        if code != 0:
            return result(PASS, "Guest account not present")
        active = re.search(r"Account active\s+(\S+)", out)
        state = active.group(1) if active else "unknown"
        return result(
            PASS if state.lower() in ("no", "nein", "non") else FAIL,
            "Guest account active: {0}".format(state),
            expected="Guest account disabled",
        )
    code, out, _ = run(["defaults", "read", "/Library/Preferences/com.apple.loginwindow",
                        "GuestEnabled"], timeout=15)
    enabled = out.strip() == "1" if code == 0 else False
    return result(FAIL if enabled else PASS,
                  "Guest login enabled: {0}".format("yes" if enabled else "no"),
                  expected="Guest account disabled")


@check("os.accounts.no_blank_passwords", ["windows", "linux", "macos"])
def check_no_blank_passwords():
    if PLATFORM == "windows":
        value = secpol("LimitBlankPasswordUse")
        if value is None:
            value = reg_int(r"HKLM\SYSTEM\CurrentControlSet\Control\Lsa", "LimitBlankPasswordUse")
        if value is None:
            return result(ERROR, "", error="could not read LimitBlankPasswordUse")
        return result(PASS if value == 1 else FAIL,
                      "LimitBlankPasswordUse = {0}".format(value),
                      expected="Blank passwords limited to console logon (value 1)")
    if PLATFORM == "linux":
        text = read_text("/etc/shadow")
        if text is None:
            return needs_root("/etc/shadow is not readable")
        blank = []
        for line in text.splitlines():
            fields = line.split(":")
            if len(fields) > 1 and fields[1] == "" and not fields[0].startswith("#"):
                blank.append(fields[0])
        return result(
            PASS if not blank else FAIL,
            "Accounts with an empty password: {0}".format(", ".join(blank) or "none"),
            expected="No enabled account may have an empty password",
            details={"accounts": blank},
        )
    code, out, _ = run(["pwpolicy", "getaccountpolicies"], timeout=20)
    if code != 0:
        return result(ERROR, "", error="pwpolicy unavailable")
    minimum = re.search(r"policyAttributeMinimumLength.*?(\d+)", out, re.S)
    length = int(minimum.group(1)) if minimum else 0
    return result(PASS if length > 0 else FAIL,
                  "Minimum password length policy: {0}".format(length),
                  expected="A minimum password length greater than zero is enforced")


@check("os.accounts.inactive_enabled", ["windows", "linux", "macos"])
def check_inactive_accounts():
    days = param("os.accounts.inactive_enabled", "inactive_days")
    users = local_users()
    if users is None:
        return needs_root("cannot enumerate local accounts")
    stale = []
    for user in users:
        if not user.get("enabled", True) or user.get("system"):
            continue
        last = user.get("last_logon_days")
        if last is not None and last > days:
            stale.append("{0} ({1} days)".format(user["name"], last))
    if not any(u.get("last_logon_days") is not None for u in users):
        return result(INFO, "Last-logon data is not available on this platform",
                      expected="No enabled local account without a logon in {0} days".format(days))
    return result(
        PASS if not stale else FAIL,
        "Inactive enabled account(s): {0}".format(", ".join(stale) or "none"),
        expected="No enabled local account without a logon in {0} days".format(days),
        details={"inactive": stale},
    )


@check("os.accounts.autologon_disabled", ["windows"])
def check_autologon():
    key = r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
    auto = reg_query(key, "AutoAdminLogon")
    stored = reg_query(key, "DefaultPassword")
    enabled = str(auto or "0").strip() in ("1", "0x1")
    return result(
        FAIL if enabled or stored else PASS,
        "AutoAdminLogon = {0}{1}".format(auto or "0",
                                         "; DefaultPassword is set" if stored else ""),
        expected="AutoAdminLogon = 0 and no stored DefaultPassword",
    )


@check("os.accounts.uac_enabled", ["windows"])
def check_uac():
    key = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
    enable_lua = reg_int(key, "EnableLUA")
    consent = reg_int(key, "ConsentPromptBehaviorAdmin")
    if enable_lua is None:
        return result(ERROR, "", error="could not read EnableLUA")
    ok = enable_lua == 1 and (consent is None or consent >= 2)
    return result(
        PASS if ok else FAIL,
        "EnableLUA = {0}, ConsentPromptBehaviorAdmin = {1}".format(enable_lua, consent),
        expected="EnableLUA = 1 and ConsentPromptBehaviorAdmin >= 2",
    )


# --------------------------------------------------------------------------------------------
# Password and lockout policy
# --------------------------------------------------------------------------------------------
def has_graphical_session():
    """True when a desktop environment is installed, so a screen lock applies at all."""
    if os.path.isdir("/usr/share/xsessions") and os.listdir("/usr/share/xsessions"):
        return True
    if os.path.isdir("/usr/share/wayland-sessions") and os.listdir("/usr/share/wayland-sessions"):
        return True
    return bool(which("Xorg") or which("gnome-shell") or which("plasmashell"))


def linux_pwquality():
    values = {}
    for path in ("/etc/security/pwquality.conf", "/etc/login.defs"):
        text = read_text(path)
        if not text:
            continue
        for line in text.splitlines():
            line = line.split("#")[0].strip()
            if not line:
                continue
            if "=" in line:
                key, _, value = line.partition("=")
            else:
                parts = line.split()
                if len(parts) < 2:
                    continue
                key, value = parts[0], parts[1]
            values[key.strip().lower()] = value.strip()
    for path in ("/etc/pam.d/common-password", "/etc/pam.d/system-auth",
                 "/etc/pam.d/password-auth"):
        text = read_text(path)
        if not text:
            continue
        for line in text.splitlines():
            if line.strip().startswith("#"):
                continue
            for match in re.finditer(r"(\w+)=(-?\w+)", line):
                values.setdefault(match.group(1).lower(), match.group(2))
    return values


@check("os.password.min_length", ["windows", "linux", "macos"])
def check_min_length():
    minimum = param("os.password.min_length", "min_length")
    expected = "Minimum password length >= {0}".format(minimum)
    if PLATFORM == "windows":
        length = secpol("MinimumPasswordLength")
        if length is None:
            code, out, _ = run(["net", "accounts"], timeout=20)
            match = re.search(r"Minimum password length:\s*(\d+)", out)
            length = int(match.group(1)) if match else None
        if length is None:
            return result(ERROR, "", expected=expected, error="could not read the password policy")
        return result(PASS if length >= minimum else FAIL,
                      "Minimum password length {0}".format(length), expected=expected)
    if PLATFORM == "linux":
        values = linux_pwquality()
        raw = values.get("minlen") or values.get("pass_min_len")
        if raw is None:
            return result(FAIL, "No minimum password length configured (pwquality or login.defs)",
                          expected=expected)
        try:
            length = int(raw)
        except ValueError:
            return result(ERROR, raw, expected=expected, error="unparsable minlen value")
        return result(PASS if length >= minimum else FAIL,
                      "Minimum password length {0}".format(length), expected=expected,
                      details={"source": "pwquality/login.defs"})
    code, out, _ = run(["pwpolicy", "getaccountpolicies"], timeout=20)
    match = re.search(r"policyAttributeMinimumLength.*?(\d+)", out or "", re.S)
    if code != 0 or not match:
        return result(FAIL, "No minimum password length policy is set", expected=expected)
    length = int(match.group(1))
    return result(PASS if length >= minimum else FAIL,
                  "Minimum password length {0}".format(length), expected=expected)


@check("os.password.complexity", ["windows", "linux", "macos"])
def check_complexity():
    expected = "Password complexity requirements enabled"
    if PLATFORM == "windows":
        value = secpol("PasswordComplexity")
        if value is None:
            return result(ERROR, "", expected=expected, error="could not read PasswordComplexity")
        return result(PASS if value == 1 else FAIL,
                      "PasswordComplexity = {0}".format(value), expected=expected)
    if PLATFORM == "linux":
        values = linux_pwquality()
        classes = values.get("minclass")
        credits = [values.get(k) for k in ("dcredit", "ucredit", "lcredit", "ocredit")]
        negative = [c for c in credits if c and str(c).lstrip("-").isdigit() and int(c) < 0]
        if classes and str(classes).isdigit() and int(classes) >= 3:
            return result(PASS, "pwquality minclass = {0}".format(classes), expected=expected)
        if len(negative) >= 3:
            return result(PASS, "pwquality character class credits: {0}".format(
                ", ".join(str(c) for c in credits if c)), expected=expected)
        return result(FAIL, "No complexity requirement found in pwquality or PAM",
                      expected=expected, details={"pwquality": values})
    code, out, _ = run(["pwpolicy", "getaccountpolicies"], timeout=20)
    text = out or ""
    has_alpha = "policyAttributeMinimumAlpha" in text or "requiresAlpha" in text
    has_numeric = "policyAttributeMinimumNumeric" in text or "requiresNumeric" in text
    if code != 0:
        return result(ERROR, "", expected=expected, error="pwpolicy unavailable")
    return result(PASS if (has_alpha and has_numeric) else FAIL,
                  "Alphabetic requirement: {0}; numeric requirement: {1}".format(has_alpha,
                                                                                 has_numeric),
                  expected=expected)


@check("os.password.history", ["windows", "linux", "macos"])
def check_history():
    generations = param("os.password.history", "history")
    expected = "Password history >= {0} generations".format(generations)
    if PLATFORM == "windows":
        value = secpol("PasswordHistorySize")
        if value is None:
            return result(ERROR, "", expected=expected, error="could not read PasswordHistorySize")
        return result(PASS if value >= generations else FAIL,
                      "PasswordHistorySize = {0}".format(value), expected=expected)
    if PLATFORM == "linux":
        values = linux_pwquality()
        remember = values.get("remember")
        if remember is None:
            return result(FAIL, "pam_pwhistory 'remember' is not configured", expected=expected)
        try:
            count = int(remember)
        except ValueError:
            return result(ERROR, str(remember), expected=expected, error="unparsable remember value")
        return result(PASS if count >= generations else FAIL,
                      "pam remember = {0}".format(count), expected=expected)
    code, out, _ = run(["pwpolicy", "getaccountpolicies"], timeout=20)
    match = re.search(r"policyAttributePasswordHistoryDepth.*?(\d+)", out or "", re.S)
    if code != 0 or not match:
        return result(FAIL, "No password history policy is set", expected=expected)
    count = int(match.group(1))
    return result(PASS if count >= generations else FAIL,
                  "Password history depth {0}".format(count), expected=expected)


@check("os.lockout.threshold", ["windows", "linux", "macos"])
def check_lockout():
    maximum = param("os.lockout.threshold", "max_threshold")
    expected = "Lockout threshold between 1 and {0} attempts".format(maximum)
    if PLATFORM == "windows":
        value = secpol("LockoutBadCount")
        if value is None:
            code, out, _ = run(["net", "accounts"], timeout=20)
            match = re.search(r"Lockout threshold:\s*(\S+)", out)
            raw = match.group(1) if match else None
            value = 0 if raw and raw.lower() == "never" else (int(raw) if raw and raw.isdigit()
                                                              else None)
        if value is None:
            return result(ERROR, "", expected=expected, error="could not read the lockout policy")
        return result(PASS if 1 <= value <= maximum else FAIL,
                      "Lockout threshold {0}".format(value or "never"), expected=expected)
    if PLATFORM == "linux":
        values = linux_pwquality()
        deny = values.get("deny")
        if deny is None:
            text = "".join(read_text(p) or "" for p in
                           ("/etc/security/faillock.conf", "/etc/pam.d/common-auth",
                            "/etc/pam.d/system-auth"))
            match = re.search(r"deny\s*=\s*(\d+)", text)
            deny = match.group(1) if match else None
        if deny is None:
            return result(FAIL, "No account lockout (pam_faillock deny) is configured",
                          expected=expected)
        count = int(deny)
        return result(PASS if 1 <= count <= maximum else FAIL,
                      "pam_faillock deny = {0}".format(count), expected=expected)
    code, out, _ = run(["pwpolicy", "getaccountpolicies"], timeout=20)
    match = re.search(r"policyAttributeMaximumFailedAuthentications.*?(\d+)", out or "", re.S)
    if code != 0 or not match:
        return result(FAIL, "No maximum failed authentication policy is set", expected=expected)
    count = int(match.group(1))
    return result(PASS if 1 <= count <= maximum else FAIL,
                  "Maximum failed authentications {0}".format(count), expected=expected)


# --------------------------------------------------------------------------------------------
# Session checks
# --------------------------------------------------------------------------------------------
@check("os.session.screen_lock", ["windows", "linux", "macos"])
def check_screen_lock():
    maximum = param("os.session.screen_lock", "max_seconds")
    expected = "Lock within {0} seconds of inactivity with a password".format(maximum)
    if PLATFORM == "windows":
        inactivity = reg_int(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System",
                             "InactivityTimeoutSecs")
        if inactivity is None:
            inactivity = secpol("MACHINE\\Software\\Microsoft\\Windows\\CurrentVersion\\"
                                "Policies\\System\\InactivityTimeoutSecs")
        timeout = reg_query(r"HKCU\Control Panel\Desktop", "ScreenSaveTimeOut")
        secure = reg_query(r"HKCU\Control Panel\Desktop", "ScreenSaverIsSecure")
        active = reg_query(r"HKCU\Control Panel\Desktop", "ScreenSaveActive")
        seconds = None
        if isinstance(inactivity, int) and inactivity > 0:
            seconds = inactivity
        elif timeout and str(timeout).isdigit():
            seconds = int(timeout)
        locked = str(secure or "0").strip() in ("1", "0x1")
        enabled = str(active or "0").strip() in ("1", "0x1") or bool(inactivity)
        ok = bool(seconds) and seconds <= maximum and locked and enabled
        return result(
            PASS if ok else FAIL,
            "Timeout {0} s, password required: {1}".format(seconds if seconds else "not set",
                                                           "yes" if locked else "no"),
            expected=expected,
            details={"InactivityTimeoutSecs": inactivity, "ScreenSaveTimeOut": timeout,
                     "ScreenSaverIsSecure": secure},
        )
    if PLATFORM == "linux":
        if not has_graphical_session():
            return result(
                NA,
                "No graphical session is installed, so there is no screen to lock; interactive "
                "sessions are covered by the idle timeout check",
                expected=expected,
            )
        code, delay, _ = run(["gsettings", "get", "org.gnome.desktop.session", "idle-delay"],
                             timeout=15)
        code2, lock, _ = run(["gsettings", "get", "org.gnome.desktop.screensaver", "lock-enabled"],
                             timeout=15)
        if code != 0 and code2 != 0:
            return result(ERROR, "", expected=expected,
                          error="a graphical session is present but its settings could not be read")
        match = re.search(r"(\d+)", delay or "")
        seconds = int(match.group(1)) if match else None
        locked = "true" in (lock or "").lower()
        ok = bool(seconds) and 0 < seconds <= maximum and locked
        return result(PASS if ok else FAIL,
                      "Idle delay {0} s, lock enabled: {1}".format(seconds, locked),
                      expected=expected)
    idle = macos_defaults("com.apple.screensaver", "idleTime", host=True)
    ask = macos_defaults("com.apple.screensaver", "askForPassword")
    delay = macos_defaults("com.apple.screensaver", "askForPasswordDelay")
    try:
        seconds = int(idle) if idle else None
    except ValueError:
        seconds = None
    ok = bool(seconds) and 0 < seconds <= maximum and str(ask) == "1"
    return result(PASS if ok else FAIL,
                  "Idle time {0} s, password required: {1} (delay {2})".format(
                      seconds, "yes" if str(ask) == "1" else "no", delay or "0"),
                  expected=expected)


@check("os.session.logon_banner", ["windows", "linux", "macos"])
def check_logon_banner():
    expected = "A logon notice is displayed before authentication"
    if PLATFORM == "windows":
        key = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
        caption = reg_query(key, "legalnoticecaption")
        text = reg_query(key, "legalnoticetext")
        ok = bool(caption) or bool(text)
        return result(PASS if ok else FAIL,
                      "Legal notice configured: {0}".format("yes" if ok else "no"),
                      expected=expected)
    sources = {}
    for path in ("/etc/issue", "/etc/issue.net", "/etc/motd"):
        content = (read_text(path, 4000) or "").strip()
        if content:
            sources[path] = content[:200]
    banner = sshd_config().get("banner", "none")
    if banner and banner not in ("none", "/dev/null"):
        sources["sshd Banner"] = banner
    if PLATFORM == "macos":
        policy = (read_text("/Library/Security/PolicyBanner.txt", 4000)
                  or read_text("/Library/Security/PolicyBanner.rtf", 4000))
        if policy:
            sources["PolicyBanner"] = policy[:200]
    return result(PASS if sources else FAIL,
                  "Banner sources: {0}".format(", ".join(sources) or "none"),
                  expected=expected, details={"sources": sources})


@check("os.session.idle_timeout", ["windows", "linux", "macos"])
def check_idle_timeout():
    maximum = param("os.session.idle_timeout", "max_seconds")
    expected = "Idle sessions terminate within {0} seconds".format(maximum)
    if PLATFORM == "windows":
        key = (r"HKLM\SOFTWARE\Policies\Microsoft\Windows NT\Terminal Services")
        idle = reg_int(key, "MaxIdleTime")
        disconnect = reg_int(key, "MaxDisconnectionTime")
        if idle is None:
            return result(FAIL, "Remote Desktop idle session limit is not configured",
                          expected=expected)
        seconds = idle / 1000.0
        return result(PASS if 0 < seconds <= maximum else FAIL,
                      "MaxIdleTime {0:.0f} s, MaxDisconnectionTime {1}".format(
                          seconds, disconnect if disconnect is not None else "not set"),
                      expected=expected)
    values = sshd_config()
    interval = values.get("clientaliveinterval")
    count = values.get("clientalivecountmax")
    tmout = None
    for path in ("/etc/profile", "/etc/profile.d/tmout.sh", "/etc/bashrc", "/etc/bash.bashrc"):
        text = read_text(path, 20000) or ""
        match = re.search(r"^\s*(?:export\s+)?TMOUT=(\d+)", text, re.M)
        if match:
            tmout = int(match.group(1))
            break
    ssh_seconds = None
    if interval and interval.isdigit() and int(interval) > 0:
        ssh_seconds = int(interval) * max(1, int(count) if count and count.isdigit() else 1)
    best = min([s for s in (tmout, ssh_seconds) if s], default=None)
    return result(
        PASS if best and best <= maximum else FAIL,
        "Shell TMOUT: {0}; sshd keepalive window: {1}".format(
            "{0} s".format(tmout) if tmout else "not set",
            "{0} s".format(ssh_seconds) if ssh_seconds else "not set"),
        expected=expected,
    )


# --------------------------------------------------------------------------------------------
# Network checks
# --------------------------------------------------------------------------------------------
def linux_firewall_state():
    """Return (name, active, default_inbound, detail)."""
    if which("ufw"):
        code, out, _ = run(["ufw", "status", "verbose"], timeout=20)
        if code == 0 and out:
            active = "status: active" in out.lower()
            match = re.search(r"Default:\s*(\w+)\s*\(incoming\)", out)
            return "ufw", active, (match.group(1).lower() if match else None), out[:400]
    if which("firewall-cmd"):
        code, out, _ = run(["firewall-cmd", "--state"], timeout=20)
        active = code == 0 and "running" in out
        code2, zone, _ = run(["firewall-cmd", "--get-default-zone"], timeout=20)
        default = zone.strip() if code2 == 0 else None
        inbound = "deny" if default in ("drop", "block") else ("allow" if default else None)
        return "firewalld", active, inbound, "default zone: {0}".format(default)
    if which("nft"):
        code, out, _ = run(["nft", "list", "ruleset"], timeout=25)
        if code == 0 and out.strip():
            match = re.search(r"type filter hook input priority \w+;\s*policy (\w+)", out)
            policy = match.group(1) if match else None
            inbound = "deny" if policy in ("drop", "reject") else ("allow" if policy else None)
            return "nftables", bool(out.strip()), inbound, "input policy: {0}".format(policy)
    if which("iptables"):
        code, out, _ = run(["iptables", "-S"], timeout=25)
        if code == 0:
            match = re.search(r"-P INPUT (\w+)", out)
            policy = match.group(1) if match else None
            inbound = "deny" if policy in ("DROP", "REJECT") else ("allow" if policy else None)
            rules = len([line for line in out.splitlines() if line.startswith("-A")])
            return "iptables", rules > 0 or policy in ("DROP", "REJECT"), inbound, \
                "INPUT policy {0}, {1} rules".format(policy, rules)
    return None, False, None, "no supported firewall tool found"


@check("os.firewall.enabled", ["windows", "linux", "macos"])
def check_firewall_enabled():
    expected = "Host firewall enabled on every profile or interface"
    if PLATFORM == "windows":
        code, out, _ = run(["netsh", "advfirewall", "show", "allprofiles"], timeout=25)
        if code != 0:
            return result(ERROR, "", expected=expected, error="netsh advfirewall failed")
        states = re.findall(r"(?m)^State\s+(\w+)", out)
        profiles = ["Domain", "Private", "Public"]
        pairs = list(zip(profiles, states)) if len(states) >= 3 else []
        ok = bool(states) and all(s.upper() == "ON" for s in states)
        observed = "; ".join("{0}: {1}".format(p, s) for p, s in pairs) or "state unavailable"
        return result(PASS if ok else FAIL, observed, expected=expected)
    if PLATFORM == "macos":
        code, out, _ = run(["/usr/libexec/ApplicationFirewall/socketfilterfw",
                            "--getglobalstate"], timeout=20)
        enabled = "enabled" in (out or "").lower()
        return result(PASS if enabled else FAIL, (out or "unknown").strip(), expected=expected)
    name, active, _, detail = linux_firewall_state()
    if name is None:
        return result(FAIL, "No host firewall is active ({0})".format(detail), expected=expected)
    return result(PASS if active else FAIL,
                  "{0} active: {1} ({2})".format(name, "yes" if active else "no", detail[:200]),
                  expected=expected)


@check("os.firewall.default_inbound_block", ["windows", "linux", "macos"])
def check_default_inbound():
    expected = "Inbound traffic denied by default"
    if PLATFORM == "windows":
        code, out, _ = run(["netsh", "advfirewall", "show", "allprofiles"], timeout=25)
        if code != 0:
            return result(ERROR, "", expected=expected, error="netsh advfirewall failed")
        actions = re.findall(r"(?m)^Firewall Policy\s+(.+)$", out)
        inbound = [a.split(",")[0].strip() for a in actions]
        ok = bool(inbound) and all("block" in value.lower() for value in inbound)
        return result(PASS if ok else FAIL,
                      "Default inbound: {0}".format("; ".join(inbound) or "unknown"),
                      expected=expected)
    if PLATFORM == "macos":
        code, out, _ = run(["/usr/libexec/ApplicationFirewall/socketfilterfw",
                            "--getblockall"], timeout=20)
        code2, stealth, _ = run(["/usr/libexec/ApplicationFirewall/socketfilterfw",
                                 "--getstealthmode"], timeout=20)
        blocked = "on" in (out or "").lower() or "enabled" in (stealth or "").lower()
        return result(PASS if blocked else FAIL,
                      "Block all incoming: {0}; stealth mode: {1}".format(
                          (out or "").strip(), (stealth or "").strip()),
                      expected=expected)
    name, _, inbound, detail = linux_firewall_state()
    if inbound is None:
        return result(FAIL, "Could not determine the default inbound policy ({0})".format(detail),
                      expected=expected)
    return result(PASS if inbound == "deny" else FAIL,
                  "{0} default inbound: {1}".format(name, inbound), expected=expected)


@check("os.remote.remote_access", ["windows", "linux", "macos"])
def check_remote_access():
    expected = "Remote access disabled, or hardened (NLA for RDP; keys and no root for SSH)"
    if PLATFORM == "windows":
        deny = reg_int(r"HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server",
                       "fDenyTSConnections")
        if deny == 1:
            return result(PASS, "Remote Desktop is disabled", expected=expected)
        key = r"HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp"
        nla = reg_int(key, "UserAuthentication")
        layer = reg_int(key, "SecurityLayer")
        ok = nla == 1
        return result(PASS if ok else FAIL,
                      "RDP enabled; NLA: {0}, SecurityLayer: {1}".format(nla, layer),
                      expected=expected)
    values = sshd_config()
    if not values:
        return result(PASS, "No SSH server configuration found (remote access not enabled)",
                      expected=expected)
    running = False
    code, out, _ = run(["pgrep", "-x", "sshd"], timeout=10)
    running = code == 0
    root_login = (values.get("permitrootlogin") or "").lower()
    password_auth = (values.get("passwordauthentication") or "").lower()
    if not running:
        return result(PASS, "sshd is not running", expected=expected)
    ok = root_login in ("no", "prohibit-password", "forced-commands-only") \
        and password_auth == "no"
    return result(PASS if ok else FAIL,
                  "sshd running; PermitRootLogin={0}, PasswordAuthentication={1}".format(
                      root_login or "default", password_auth or "default"),
                  expected=expected)


@check("os.services.legacy_protocols", ["windows", "linux", "macos"])
def check_legacy_protocols():
    expected = "Telnet, FTP, rsh/rlogin, TFTP and SMBv1 are not enabled"
    found = []
    if PLATFORM == "windows":
        code, out, _ = powershell(
            "$r=@(); try{ if((Get-SmbServerConfiguration -ErrorAction Stop).EnableSMB1Protocol)"
            "{$r+='SMB1'} }catch{}; "
            "foreach($f in 'TelnetClient','TelnetServer','TFTP'){ try{ "
            "if((Get-WindowsOptionalFeature -Online -FeatureName $f -ErrorAction Stop).State "
            "-eq 'Enabled'){$r+=$f} }catch{} }; $r -join ','"
        )
        if code != 0:
            return result(ERROR, "", expected=expected, error="could not query Windows features")
        found = [f for f in (out or "").split(",") if f.strip()]
    else:
        ports = listening_ports() or []
        risky = {21: "FTP", 23: "Telnet", 69: "TFTP", 512: "rexec", 513: "rlogin", 514: "rsh"}
        for entry in ports:
            if entry["port"] in risky:
                found.append("{0} (port {1})".format(risky[entry["port"]], entry["port"]))
        for binary in ("telnetd", "in.telnetd", "vsftpd", "rshd"):
            if which(binary):
                found.append(binary)
    return result(PASS if not found else FAIL,
                  "Legacy services found: {0}".format(", ".join(sorted(set(found))) or "none"),
                  expected=expected, details={"found": sorted(set(found))})


@check("os.time.sync", ["windows", "linux", "macos"])
def check_time_sync():
    hours = param("os.time.sync", "max_hours")
    expected = "Clock synchronized with an authoritative source within {0} hours".format(hours)
    if PLATFORM == "windows":
        code, out, _ = run(["w32tm", "/query", "/status"], timeout=25)
        if code != 0:
            return result(FAIL, "Windows Time service is not running or not configured",
                          expected=expected)
        source = re.search(r"Source:\s*(.+)", out)
        last = re.search(r"Last Successful Sync Time:\s*(.+)", out)
        synced = bool(last and "unspecified" not in last.group(1).lower())
        return result(PASS if synced else FAIL,
                      "Source: {0}; last sync: {1}".format(
                          source.group(1).strip() if source else "unknown",
                          last.group(1).strip() if last else "never"),
                      expected=expected)
    if PLATFORM == "macos":
        code, out, _ = run(["systemsetup", "-getusingnetworktime"], timeout=20)
        if code != 0:
            return needs_root("systemsetup requires administrative rights")
        on = "on" in (out or "").lower()
        code2, server, _ = run(["systemsetup", "-getnetworktimeserver"], timeout=20)
        return result(PASS if on else FAIL,
                      "Network time: {0}; {1}".format((out or "").strip(), (server or "").strip()),
                      expected=expected)
    code, out, _ = run(["timedatectl", "show"], timeout=20)
    if code == 0 and out:
        values = parse_key_values(out)
        synced = values.get("ntpsynchronized", "no").lower() in ("yes", "true", "1")
        enabled = values.get("ntp", "no").lower() in ("yes", "true", "1")
        return result(PASS if (synced and enabled) else FAIL,
                      "NTP enabled: {0}, synchronized: {1}".format(enabled, synced),
                      expected=expected)
    for command in (["chronyc", "tracking"], ["ntpq", "-p"]):
        if which(command[0]):
            code, out, _ = run(command, timeout=20)
            if code == 0 and out.strip():
                return result(PASS, "{0} reports a time source".format(command[0]),
                              expected=expected, details={"output": out[:400]})
    return result(FAIL, "No time synchronization service found", expected=expected)


# --------------------------------------------------------------------------------------------
# Audit checks
# --------------------------------------------------------------------------------------------
def windows_auditpol():
    code, out, _ = run(["auditpol", "/get", "/category:*"], timeout=45)
    if code != 0:
        return None
    settings = {}
    for line in out.splitlines():
        match = re.match(r"\s{2,}(\S.*?)\s{2,}(No Auditing|Success and Failure|Success|Failure)\s*$",
                         line)
        if match:
            settings[match.group(1).strip().lower()] = match.group(2).strip()
    return settings


@check("os.audit.logging_enabled", ["windows", "linux", "macos"])
def check_audit_logging():
    expected = "Logon, account management and policy change events are audited"
    if PLATFORM == "windows":
        settings = windows_auditpol()
        if settings is None:
            return needs_root("auditpol requires an elevated session")
        wanted = ["logon", "user account management", "audit policy change"]
        missing = [name for name in wanted
                   if settings.get(name, "No Auditing") == "No Auditing"]
        return result(PASS if not missing else FAIL,
                      "Subcategories without auditing: {0}".format(", ".join(missing) or "none"),
                      expected=expected, details={"auditpol": settings})
    if PLATFORM == "macos":
        code, out, _ = run(["launchctl", "list"], timeout=20)
        running = "auditd" in (out or "")
        return result(PASS if running else INFO,
                      "auditd running: {0} (macOS unified logging is always on)".format(running),
                      expected=expected)
    code, out, _ = run(["systemctl", "is-active", "auditd"], timeout=15)
    auditd = code == 0 and "active" in out
    code2, out2, _ = run(["systemctl", "is-active", "systemd-journald"], timeout=15)
    journald = code2 == 0 and "active" in out2
    return result(PASS if (auditd or journald) else FAIL,
                  "auditd active: {0}; journald active: {1}".format(auditd, journald),
                  expected=expected)


@check("os.audit.log_retention", ["windows", "linux", "macos"])
def check_log_retention():
    megabytes = param("os.audit.log_retention", "min_mb")
    expected = "Security log at least {0} MB and retained".format(megabytes)
    if PLATFORM == "windows":
        size = reg_int(r"HKLM\SYSTEM\CurrentControlSet\Services\EventLog\Security", "MaxSize")
        retention = reg_query(r"HKLM\SYSTEM\CurrentControlSet\Services\EventLog\Security",
                              "Retention")
        if size is None:
            return result(ERROR, "", expected=expected, error="could not read the Security log size")
        actual = size / (1024.0 * 1024.0)
        return result(PASS if actual >= megabytes else FAIL,
                      "Security log max size {0:.0f} MB (retention {1})".format(
                          actual, retention or "default"),
                      expected=expected)
    if PLATFORM == "macos":
        return result(INFO, "macOS unified logging retains system logs by default",
                      expected=expected)
    text = read_text("/etc/systemd/journald.conf") or ""
    storage = re.search(r"(?m)^\s*Storage\s*=\s*(\w+)", text)
    persistent = (storage.group(1).lower() == "persistent" if storage
                  else os.path.isdir("/var/log/journal"))
    auditd = read_text("/etc/audit/auditd.conf") or ""
    action = re.search(r"(?m)^\s*max_log_file_action\s*=\s*(\w+)", auditd)
    return result(PASS if persistent else FAIL,
                  "journald persistent storage: {0}; auditd max_log_file_action: {1}".format(
                      persistent, action.group(1) if action else "not set"),
                  expected=expected)


@check("os.audit.privileged_actions", ["windows", "linux", "macos"])
def check_privileged_auditing():
    expected = "Use of privileged functions is audited"
    if PLATFORM == "windows":
        settings = windows_auditpol()
        if settings is None:
            return needs_root("auditpol requires an elevated session")
        privilege = settings.get("sensitive privilege use", "No Auditing")
        process = settings.get("process creation", "No Auditing")
        ok = privilege != "No Auditing" or process != "No Auditing"
        return result(PASS if ok else FAIL,
                      "Sensitive Privilege Use: {0}; Process Creation: {1}".format(privilege,
                                                                                   process),
                      expected=expected)
    rules = read_text("/etc/audit/rules.d/audit.rules") or read_text("/etc/audit/audit.rules") or ""
    sudoers = os.path.isfile("/etc/sudoers")
    logfile = re.search(r"logfile\s*=\s*(\S+)", read_text("/etc/sudoers") or "")
    has_execve = "execve" in rules
    ok = has_execve or bool(logfile) or (sudoers and PLATFORM == "macos")
    return result(PASS if ok else FAIL,
                  "auditd execve rules: {0}; sudo logfile: {1}".format(
                      has_execve, logfile.group(1) if logfile else "system default"),
                  expected=expected)


@check("os.audit.powershell_logging", ["windows"])
def check_powershell_logging():
    value = reg_int(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging",
                    "EnableScriptBlockLogging")
    return result(PASS if value == 1 else FAIL,
                  "EnableScriptBlockLogging = {0}".format(value if value is not None else "not set"),
                  expected="PowerShell script block logging enabled")


# --------------------------------------------------------------------------------------------
# Endpoint protection and patching
# --------------------------------------------------------------------------------------------
def defender_status():
    code, out, _ = powershell(
        "try{ $s=Get-MpComputerStatus -ErrorAction Stop; "
        "[pscustomobject]@{rt=$s.RealTimeProtectionEnabled; age=$s.AntivirusSignatureAge; "
        "quick=$s.QuickScanEndTime; full=$s.FullScanEndTime; mode=$s.AMRunningMode} "
        "| ConvertTo-Json -Compress }catch{ '' }"
    )
    if code != 0 or not out or not out.startswith("{"):
        return None
    try:
        return json.loads(out)
    except ValueError:
        return None


@check("os.malware.protection_enabled", ["windows", "linux", "macos"])
def check_malware_protection():
    expected = "Anti-malware present with real-time protection enabled"
    if PLATFORM == "windows":
        status = defender_status()
        if status is not None:
            enabled = bool(status.get("rt"))
            return result(PASS if enabled else FAIL,
                          "Defender real-time protection: {0} (mode {1})".format(
                              "on" if enabled else "off", status.get("mode", "unknown")),
                          expected=expected, details=status)
        code, out, _ = powershell(
            "try{ (Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct "
            "-ErrorAction Stop | Select-Object -ExpandProperty displayName) -join ',' }catch{ '' }"
        )
        products = [p for p in (out or "").split(",") if p.strip()]
        return result(PASS if products else FAIL,
                      "Registered anti-virus products: {0}".format(", ".join(products) or "none"),
                      expected=expected)
    if PLATFORM == "macos":
        code, out, _ = run(["pgrep", "-l", "-f", "Defender|Falcon|SentinelOne|clamd"], timeout=15,
                           shell=False)
        running = [line for line in (out or "").splitlines() if line.strip()]
        return result(PASS if running else INFO,
                      "Endpoint protection processes: {0}".format(
                          "; ".join(running)[:200] or "none found (XProtect is built in)"),
                      expected=expected)
    candidates = ("clamd", "freshclam", "falcon-sensor", "sentinelone", "mdatp")
    found = [name for name in candidates if which(name)]
    code, out, _ = run(["pgrep", "-l", "-f", "clamd|falcon|mdatp|sentinel"], timeout=15)
    processes = [line for line in (out or "").splitlines() if line.strip()]
    ok = bool(found or processes)
    return result(PASS if ok else FAIL,
                  "Anti-malware present: {0}".format(", ".join(found + processes)[:200] or "none"),
                  expected=expected)


@check("os.malware.signatures_current", ["windows", "linux", "macos"])
def check_signatures():
    days = param("os.malware.signatures_current", "max_days")
    expected = "Signatures updated within {0} days".format(days)
    if PLATFORM == "windows":
        status = defender_status()
        if status is None:
            return result(ERROR, "", expected=expected, error="anti-malware status unavailable")
        age = status.get("age")
        if age is None:
            return result(ERROR, "", expected=expected, error="signature age unavailable")
        return result(PASS if age <= days else FAIL,
                      "Signatures {0} day(s) old".format(age), expected=expected)
    for path in ("/var/lib/clamav/daily.cvd", "/var/lib/clamav/daily.cld",
                 "/usr/local/share/clamav/daily.cvd"):
        if os.path.isfile(path):
            age = days_since(datetime.utcfromtimestamp(os.path.getmtime(path)))
            return result(PASS if age <= days else FAIL,
                          "ClamAV definitions {0} day(s) old".format(age), expected=expected)
    return result(INFO, "No signature database found to age-check on this platform",
                  expected=expected)


@check("os.malware.last_scan", ["windows", "linux", "macos"])
def check_last_scan():
    days = param("os.malware.last_scan", "max_days")
    expected = "A malware scan ran within {0} days".format(days)
    if PLATFORM == "windows":
        status = defender_status()
        if status is None:
            return result(ERROR, "", expected=expected, error="anti-malware status unavailable")
        stamp = status.get("quick") or status.get("full")
        if not stamp:
            return result(FAIL, "No completed scan is recorded", expected=expected)
        match = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(stamp))
        if not match:
            return result(INFO, "Last scan: {0}".format(stamp), expected=expected)
        scanned = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        age = days_since(scanned)
        return result(PASS if age <= days else FAIL,
                      "Last scan {0} day(s) ago".format(age), expected=expected)
    for path in ("/var/log/clamav/clamav.log", "/var/log/clamd.scan"):
        if os.path.isfile(path):
            age = days_since(datetime.utcfromtimestamp(os.path.getmtime(path)))
            return result(PASS if age <= days else FAIL,
                          "Last scan log written {0} day(s) ago".format(age), expected=expected)
    return result(INFO, "No scan history found on this platform", expected=expected)


@check("os.patch.last_update", ["windows", "linux", "macos"])
def check_last_update():
    days = param("os.patch.last_update", "max_days")
    expected = "An operating system update was installed within {0} days".format(days)
    if PLATFORM == "windows":
        code, out, _ = powershell(
            "try{ (Get-HotFix | Sort-Object InstalledOn -Descending | "
            "Select-Object -First 1 -ExpandProperty InstalledOn).ToString('yyyy-MM-dd') }catch{ '' }"
        )
        match = re.search(r"(\d{4})-(\d{2})-(\d{2})", out or "")
        if not match:
            return result(ERROR, "", expected=expected, error="could not read the update history")
        installed = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        age = days_since(installed)
        return result(PASS if age <= days else FAIL,
                      "Most recent hotfix installed {0} day(s) ago".format(age), expected=expected)
    if PLATFORM == "macos":
        code, out, _ = run(["softwareupdate", "--history"], timeout=45)
        match = re.search(r"(\d{2}/\d{2}/\d{4})", out or "")
        if not match:
            return result(INFO, "No update history available", expected=expected)
        month, day, year = match.group(1).split("/")
        age = days_since(datetime(int(year), int(month), int(day)))
        return result(PASS if age <= days else FAIL,
                      "Most recent update {0} day(s) ago".format(age), expected=expected)
    newest = None
    for path in ("/var/log/dpkg.log", "/var/log/yum.log", "/var/log/dnf.rpm.log",
                 "/var/lib/rpm/Packages", "/var/lib/dpkg/status"):
        if os.path.isfile(path):
            stamp = datetime.utcfromtimestamp(os.path.getmtime(path))
            newest = stamp if newest is None or stamp > newest else newest
    if newest is None:
        return result(ERROR, "", expected=expected, error="no package manager history found")
    age = days_since(newest)
    return result(PASS if age <= days else FAIL,
                  "Package database last changed {0} day(s) ago".format(age), expected=expected)


@check("os.patch.pending_updates", ["windows", "linux", "macos"])
def check_pending_updates():
    expected = "No outstanding security updates"
    if PLATFORM == "windows":
        code, out, _ = powershell(
            "try{ $s=(New-Object -ComObject Microsoft.Update.Session).CreateUpdateSearcher(); "
            "($s.Search('IsInstalled=0 and IsHidden=0').Updates).Count }catch{ 'error' }",
            timeout=120,
        )
        if (out or "").strip().isdigit():
            count = int(out.strip())
            return result(PASS if count == 0 else FAIL,
                          "{0} update(s) pending".format(count), expected=expected)
        return result(ERROR, "", expected=expected,
                      error="Windows Update search did not complete")
    if PLATFORM == "macos":
        code, out, err = run(["softwareupdate", "-l"], timeout=120)
        text = (out or "") + (err or "")
        if "No new software available" in text:
            return result(PASS, "No updates available", expected=expected)
        labels = re.findall(r"(?m)^\s*\*\s*Label:\s*(.+)$", text)
        if labels:
            return result(FAIL, "{0} update(s) available: {1}".format(len(labels),
                                                                      ", ".join(labels[:5])),
                          expected=expected)
        return result(INFO, "Could not determine pending updates", expected=expected)
    if which("apt-get"):
        code, out, _ = run(["apt-get", "-s", "upgrade"], timeout=90)
        match = re.search(r"(\d+) upgraded, (\d+) newly installed", out or "")
        if match:
            count = int(match.group(1))
            security = len(re.findall(r"(?m)^Inst .*security", out or ""))
            return result(PASS if count == 0 else FAIL,
                          "{0} package(s) upgradable ({1} security)".format(count, security),
                          expected=expected)
    if which("dnf") or which("yum"):
        tool = "dnf" if which("dnf") else "yum"
        code, out, _ = run([tool, "-q", "check-update"], timeout=120)
        if code == 0:
            return result(PASS, "No updates available", expected=expected)
        if code == 100:
            lines = [ln for ln in (out or "").splitlines() if ln.strip() and not ln.startswith(" ")]
            return result(FAIL, "{0} package update(s) available".format(len(lines)),
                          expected=expected)
    return result(ERROR, "", expected=expected, error="no supported package manager found")


@check("os.patch.auto_update", ["windows", "linux", "macos"])
def check_auto_update():
    expected = "Automatic updates enabled or managed centrally"
    if PLATFORM == "windows":
        key = r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU"
        no_auto = reg_int(key, "NoAutoUpdate")
        options = reg_int(key, "AUOptions")
        wsus = reg_query(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate", "WUServer")
        if no_auto == 1:
            return result(FAIL, "NoAutoUpdate = 1 (automatic updates disabled)", expected=expected)
        if options in (3, 4) or wsus:
            return result(PASS, "AUOptions = {0}{1}".format(
                options, "; managed by WSUS" if wsus else ""), expected=expected)
        if options is None and no_auto is None:
            return result(PASS, "Windows Update is at its default (automatic)", expected=expected)
        return result(FAIL, "AUOptions = {0}".format(options), expected=expected)
    if PLATFORM == "macos":
        auto = macos_defaults("/Library/Preferences/com.apple.SoftwareUpdate",
                              "AutomaticCheckEnabled")
        install = macos_defaults("/Library/Preferences/com.apple.SoftwareUpdate",
                                 "AutomaticallyInstallMacOSUpdates")
        ok = str(auto) == "1"
        return result(PASS if ok else FAIL,
                      "AutomaticCheckEnabled: {0}; AutomaticallyInstallMacOSUpdates: {1}".format(
                          auto, install), expected=expected)
    unattended = read_text("/etc/apt/apt.conf.d/20auto-upgrades") or ""
    if "Unattended-Upgrade\"" in unattended or "Unattended-Upgrade \"1\"" in unattended:
        enabled = '"1"' in unattended
        return result(PASS if enabled else FAIL,
                      "unattended-upgrades configured: {0}".format(enabled), expected=expected)
    dnf_auto = read_text("/etc/dnf/automatic.conf") or ""
    if dnf_auto:
        applied = re.search(r"(?m)^\s*apply_updates\s*=\s*(\w+)", dnf_auto)
        value = (applied.group(1).lower() if applied else "no")
        return result(PASS if value == "yes" else FAIL,
                      "dnf-automatic apply_updates = {0}".format(value), expected=expected)
    return result(FAIL, "No automatic update mechanism found", expected=expected)


#: Releases that no longer receive security updates, or the date they stop.
WINDOWS_EOL = {"6.1": "Windows 7", "6.2": "Windows 8", "6.3": "Windows 8.1"}


@check("os.patch.os_supported", ["windows", "linux", "macos"])
def check_os_supported():
    expected = "The operating system release still receives security updates"
    name = os_name()
    if PLATFORM == "windows":
        version = platform.version()
        build = 0
        match = re.search(r"\.(\d+)$", version)
        if match:
            build = int(match.group(1))
        release = platform.release()
        if release in WINDOWS_EOL:
            return result(FAIL, "{0} is end of life".format(WINDOWS_EOL[release]), expected=expected)
        if "LTSC" in name or "IoT" in name:
            return result(INFO, "{0} (long-term servicing channel: check the vendor lifecycle "
                                "date)".format(name), expected=expected)
        if build and build < 22000 and "10" in name:
            return result(FAIL, "{0} (build {1}): Windows 10 left support on 2025-10-14".format(
                name, build), expected=expected)
        return result(PASS, "{0} (build {1})".format(name, build or "unknown"), expected=expected)
    if PLATFORM == "macos":
        version = platform.mac_ver()[0] or "0"
        major = int(version.split(".")[0]) if version.split(".")[0].isdigit() else 0
        return result(PASS if major >= 14 else FAIL,
                      "macOS {0}{1}".format(version,
                                            "" if major >= 14 else " (older than the supported N-2)"),
                      expected=expected)
    text = read_text("/etc/os-release") or ""
    values = parse_key_values(text)
    pretty = values.get("pretty_name", name).strip('"')
    unsupported = ("Ubuntu 16.04", "Ubuntu 18.04", "CentOS Linux 7", "CentOS Linux 8",
                   "Debian GNU/Linux 9", "Debian GNU/Linux 10")
    bad = [tag for tag in unsupported if tag in pretty]
    return result(FAIL if bad else PASS, pretty, expected=expected)


# --------------------------------------------------------------------------------------------
# Cryptography and media
# --------------------------------------------------------------------------------------------
@check("os.disk.encryption", ["windows", "linux", "macos"])
def check_disk_encryption():
    expected = "The system volume is encrypted"
    if PLATFORM == "windows":
        code, out, _ = powershell(
            "try{ (Get-BitLockerVolume -MountPoint $env:SystemDrive).VolumeStatus }catch{ '' }"
        )
        if out:
            ok = "fullyencrypted" in out.replace(" ", "").lower()
            return result(PASS if ok else FAIL,
                          "{0}: {1}".format(os.environ.get("SystemDrive", "C:"), out.strip()),
                          expected=expected)
        code, out, _ = run(["manage-bde", "-status", os.environ.get("SystemDrive", "C:")],
                           timeout=45)
        if code != 0:
            return result(ERROR, "", expected=expected, error="BitLocker status unavailable")
        match = re.search(r"Conversion Status:\s*(.+)", out)
        state = match.group(1).strip() if match else "unknown"
        return result(PASS if "fully encrypted" in state.lower() else FAIL,
                      "Conversion status: {0}".format(state), expected=expected)
    if PLATFORM == "macos":
        code, out, _ = run(["fdesetup", "status"], timeout=25)
        on = "filevault is on" in (out or "").lower()
        return result(PASS if on else FAIL, (out or "unknown").strip(), expected=expected)
    code, out, _ = run(["lsblk", "-o", "NAME,TYPE,MOUNTPOINT"], timeout=25)
    if code != 0:
        return result(ERROR, "", expected=expected, error="lsblk unavailable")
    encrypted = "crypt" in (out or "")
    return result(PASS if encrypted else FAIL,
                  "LUKS/dm-crypt volume present: {0}".format("yes" if encrypted else "no"),
                  expected=expected, details={"lsblk": (out or "")[:600]})


@check("os.crypto.fips_mode", ["windows", "linux"])
def check_fips_mode():
    expected = "The operating system runs its cryptography in FIPS mode"
    if PLATFORM == "windows":
        value = reg_int(r"HKLM\SYSTEM\CurrentControlSet\Control\Lsa\FipsAlgorithmPolicy", "Enabled")
        if value is None:
            return result(FAIL, "FipsAlgorithmPolicy is not set", expected=expected)
        return result(PASS if value == 1 else FAIL,
                      "FipsAlgorithmPolicy Enabled = {0}".format(value), expected=expected)
    text = read_text("/proc/sys/crypto/fips_enabled", 16)
    if text is None:
        return result(FAIL, "/proc/sys/crypto/fips_enabled is absent (kernel not in FIPS mode)",
                      expected=expected)
    enabled = text.strip() == "1"
    return result(PASS if enabled else FAIL,
                  "fips_enabled = {0}".format(text.strip()), expected=expected)


@check("os.crypto.legacy_tls_disabled", ["windows"])
def check_legacy_tls():
    expected = "SSL 2.0/3.0 and TLS 1.0/1.1 are disabled"
    base = r"HKLM\SYSTEM\CurrentControlSet\Control\SecurityProviders\SCHANNEL\Protocols"
    enabled = []
    for protocol in ("SSL 2.0", "SSL 3.0", "TLS 1.0", "TLS 1.1"):
        for role in ("Server", "Client"):
            path = "{0}\\{1}\\{2}".format(base, protocol, role)
            value = reg_int(path, "Enabled")
            disabled_by_default = reg_int(path, "DisabledByDefault")
            if value is None and disabled_by_default is None:
                enabled.append("{0} {1} (not configured)".format(protocol, role))
            elif value not in (0, None):
                enabled.append("{0} {1}".format(protocol, role))
    return result(PASS if not enabled else FAIL,
                  "Legacy protocols still enabled or unconfigured: {0}".format(
                      ", ".join(enabled) or "none"),
                  expected=expected)


@check("os.crypto.smb_signing", ["windows"])
def check_smb_signing():
    expected = "SMB signing is required on the server and the workstation"
    server = reg_int(r"HKLM\SYSTEM\CurrentControlSet\Services\LanManServer\Parameters",
                     "RequireSecuritySignature")
    client = reg_int(r"HKLM\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters",
                     "RequireSecuritySignature")
    ok = server == 1 and client == 1
    return result(PASS if ok else FAIL,
                  "Server RequireSecuritySignature = {0}; client = {1}".format(server, client),
                  expected=expected)


@check("os.media.usb_storage_blocked", ["windows", "linux", "macos"])
def check_usb_storage():
    expected = "USB mass storage is blocked or restricted by policy"
    if PLATFORM == "windows":
        start = reg_int(r"HKLM\SYSTEM\CurrentControlSet\Services\USBSTOR", "Start")
        deny_all = reg_int(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\RemovableStorageDevices",
                           "Deny_All")
        blocked = start == 4 or deny_all == 1
        return result(PASS if blocked else FAIL,
                      "USBSTOR Start = {0}; RemovableStorageDevices Deny_All = {1}".format(
                          start, deny_all), expected=expected)
    if PLATFORM == "macos":
        return result(INFO, "Removable media restrictions are enforced by MDM profile on macOS",
                      expected=expected)
    blacklisted = False
    for directory in ("/etc/modprobe.d",):
        if os.path.isdir(directory):
            for name in os.listdir(directory):
                text = read_text(os.path.join(directory, name), 20000) or ""
                if re.search(r"(?m)^\s*(blacklist|install)\s+usb[-_]storage", text):
                    blacklisted = True
    return result(PASS if blacklisted else FAIL,
                  "usb-storage blacklisted in modprobe: {0}".format("yes" if blacklisted else "no"),
                  expected=expected)


@check("os.media.autorun_disabled", ["windows"])
def check_autorun():
    expected = "AutoRun and AutoPlay are disabled"
    policies = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer"
    drive_types = reg_int(policies, "NoDriveTypeAutoRun")
    no_autorun = reg_int(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\Explorer", "NoAutorun")
    ok = drive_types == 255 or no_autorun == 1
    return result(PASS if ok else FAIL,
                  "NoDriveTypeAutoRun = {0}; NoAutorun = {1}".format(drive_types, no_autorun),
                  expected=expected)


@check("os.platform.gatekeeper", ["macos"])
def check_gatekeeper():
    code, out, _ = run(["spctl", "--status"], timeout=20)
    enabled = "assessments enabled" in (out or "").lower()
    return result(PASS if enabled else FAIL, (out or "unknown").strip(),
                  expected="Gatekeeper assessments enabled")


@check("os.platform.sip", ["macos"])
def check_sip():
    code, out, _ = run(["csrutil", "status"], timeout=20)
    enabled = "status: enabled" in (out or "").lower()
    return result(PASS if enabled else FAIL, (out or "unknown").strip(),
                  expected="System Integrity Protection enabled")


@check("os.platform.secure_boot", ["windows", "linux"])
def check_secure_boot():
    expected = "Secure Boot is enabled"
    if PLATFORM == "windows":
        code, out, err = powershell("try{ Confirm-SecureBootUEFI }catch{ 'error' }")
        value = (out or "").strip().lower()
        if value == "true":
            return result(PASS, "Secure Boot enabled", expected=expected)
        if value == "false":
            return result(FAIL, "Secure Boot disabled", expected=expected)
        return result(NA, "Not a UEFI system or Secure Boot state unavailable", expected=expected)
    if which("mokutil"):
        code, out, _ = run(["mokutil", "--sb-state"], timeout=20)
        if code == 0 and out:
            enabled = "enabled" in out.lower()
            return result(PASS if enabled else FAIL, out.strip(), expected=expected)
    for name in os.listdir("/sys/firmware/efi/efivars") if os.path.isdir(
            "/sys/firmware/efi/efivars") else []:
        if name.startswith("SecureBoot-"):
            data = None
            try:
                with open(os.path.join("/sys/firmware/efi/efivars", name), "rb") as handle:
                    data = handle.read()
            except OSError:
                pass
            if data and len(data) >= 5:
                enabled = data[4] == 1
                return result(PASS if enabled else FAIL,
                              "SecureBoot EFI variable = {0}".format(data[4]), expected=expected)
    if not os.path.isdir("/sys/firmware/efi"):
        return result(NA, "Legacy BIOS system: Secure Boot does not apply", expected=expected)
    return result(ERROR, "", expected=expected, error="could not read the Secure Boot state")


# --------------------------------------------------------------------------------------------
# Inventory collection
# --------------------------------------------------------------------------------------------
def os_name():
    if PLATFORM == "windows":
        code, out, _ = run(["cmd", "/c", "ver"], timeout=15)
        caption = None
        code2, out2, _ = powershell(
            "try{ (Get-CimInstance Win32_OperatingSystem).Caption }catch{ '' }", timeout=30)
        if out2:
            caption = out2.strip()
        return caption or (out or "").strip() or "Windows"
    if PLATFORM == "macos":
        return "macOS {0}".format(platform.mac_ver()[0] or platform.release())
    values = parse_key_values(read_text("/etc/os-release") or "")
    return (values.get("pretty_name") or values.get("name") or "Linux").strip('"')


def local_users():
    """[{name, enabled, admin, last_logon_days, system}] or None when unavailable."""
    users = []
    if PLATFORM == "windows":
        code, out, _ = powershell(
            "try{ $admins=@((Get-LocalGroupMember -Group 'Administrators' -ErrorAction Stop)."
            "Name | ForEach-Object { ($_ -split '\\\\')[-1] }); "
            "Get-LocalUser | ForEach-Object { [pscustomobject]@{name=$_.Name; enabled=$_.Enabled; "
            "admin=($admins -contains $_.Name); last=$(if($_.LastLogon){"
            "((Get-Date)-$_.LastLogon).Days}else{$null})} } | ConvertTo-Json -Compress }catch{ '' }",
            timeout=60,
        )
        if out and out.strip().startswith(("[", "{")):
            try:
                data = json.loads(out)
            except ValueError:
                data = None
            if data is not None:
                if isinstance(data, dict):
                    data = [data]
                for entry in data:
                    users.append({
                        "name": entry.get("name"),
                        "enabled": bool(entry.get("enabled")),
                        "admin": bool(entry.get("admin")),
                        "last_logon_days": entry.get("last"),
                        "system": False,
                    })
                return users
        code, out, _ = run(["net", "localgroup", "Administrators"], timeout=25)
        admins = []
        if code == 0:
            capture = False
            for line in out.splitlines():
                if line.startswith("---"):
                    capture = True
                    continue
                if capture and line.strip() and not line.startswith("The command"):
                    admins.append(line.strip())
        return [{"name": name, "enabled": True, "admin": True, "last_logon_days": None,
                 "system": False} for name in admins] or None
    if PLATFORM == "macos":
        code, out, _ = run(["dscl", ".", "-list", "/Users"], timeout=25)
        if code != 0:
            return None
        code2, admin_out, _ = run(["dscl", ".", "-read", "/Groups/admin", "GroupMembership"],
                                  timeout=25)
        admins = set((admin_out or "").replace("GroupMembership:", "").split())
        for name in (out or "").split():
            if name.startswith("_") or name in ("daemon", "nobody", "root"):
                continue
            users.append({"name": name, "enabled": True, "admin": name in admins,
                          "last_logon_days": None, "system": False})
        return users
    text = read_text("/etc/passwd")
    if text is None:
        return None
    admins = set()
    group_text = read_text("/etc/group") or ""
    for line in group_text.splitlines():
        fields = line.split(":")
        if len(fields) >= 4 and fields[0] in ("sudo", "wheel", "admin"):
            admins.update(m for m in fields[3].split(",") if m)
    shadow = read_text("/etc/shadow")
    password_locked = set()
    if shadow:
        for line in shadow.splitlines():
            fields = line.split(":")
            if len(fields) > 1 and fields[1].startswith(("!", "*", "!!")):
                password_locked.add(fields[0])
    last_logins = {}
    code, out, _ = run(["lastlog"], timeout=30)
    if code == 0:
        for line in (out or "").splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and "Never" in line:
                last_logins[parts[0]] = None
    for line in text.splitlines():
        fields = line.split(":")
        if len(fields) < 7:
            continue
        name, uid, shell = fields[0], fields[2], fields[6]
        try:
            uid_number = int(uid)
        except ValueError:
            continue
        system_account = uid_number < 1000 and name != "root"
        # An account with a login shell can still be used with an SSH key even when its password
        # is locked, so a locked password alone does not make it disabled.
        enabled = not shell.endswith(("nologin", "false", "/bin/sync", "/bin/true"))
        users.append({
            "name": name,
            "enabled": enabled,
            "admin": name in admins or name == "root",
            "password_locked": name in password_locked,
            "last_logon_days": None,
            "system": system_account,
        })
    return users


def installed_software():
    software = []
    if PLATFORM == "windows":
        code, out, _ = powershell(
            "$p='HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
            "'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'; "
            "try{ Get-ItemProperty $p -ErrorAction SilentlyContinue | "
            "Where-Object { $_.DisplayName } | Select-Object "
            "@{n='name';e={$_.DisplayName}},@{n='version';e={$_.DisplayVersion}},"
            "@{n='publisher';e={$_.Publisher}} | ConvertTo-Json -Compress }catch{ '' }",
            timeout=90,
        )
        if out and out.strip().startswith(("[", "{")):
            try:
                data = json.loads(out)
                return data if isinstance(data, list) else [data]
            except ValueError:
                return []
        return []
    if PLATFORM == "macos":
        code, out, _ = run(["ls", "/Applications"], timeout=25)
        for name in (out or "").splitlines():
            if name.endswith(".app"):
                software.append({"name": name[:-4], "version": None, "publisher": None})
        return software
    if which("dpkg-query"):
        code, out, _ = run(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Maintainer}\n"],
                           timeout=60)
        for line in (out or "").splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                software.append({"name": parts[0], "version": parts[1],
                                 "publisher": parts[2] if len(parts) > 2 else None})
        return software
    if which("rpm"):
        code, out, _ = run(["rpm", "-qa", "--qf", "%{NAME}\t%{VERSION}-%{RELEASE}\t%{VENDOR}\n"],
                           timeout=60)
        for line in (out or "").splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                software.append({"name": parts[0], "version": parts[1],
                                 "publisher": parts[2] if len(parts) > 2 else None})
        return software
    return software


def listening_ports():
    ports = []
    if PLATFORM == "windows":
        code, out, _ = powershell(
            "try{ $t=Get-NetTCPConnection -State Listen -ErrorAction Stop | Select-Object "
            "@{n='proto';e={'tcp'}},@{n='port';e={$_.LocalPort}},"
            "@{n='process';e={(Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue)"
            ".ProcessName}}; $t | ConvertTo-Json -Compress }catch{ '' }",
            timeout=60,
        )
        if out and out.strip().startswith(("[", "{")):
            try:
                data = json.loads(out)
                return data if isinstance(data, list) else [data]
            except ValueError:
                return []
        code, out, _ = run(["netstat", "-ano"], timeout=45)
        for line in (out or "").splitlines():
            if "LISTENING" in line:
                parts = line.split()
                if len(parts) >= 2 and ":" in parts[1]:
                    try:
                        ports.append({"proto": parts[0].lower(),
                                      "port": int(parts[1].rsplit(":", 1)[1]), "process": None})
                    except ValueError:
                        pass
        return ports
    if which("ss"):
        code, out, _ = run(["ss", "-lntup"], timeout=30)
    elif which("netstat"):
        code, out, _ = run(["netstat", "-lntup"], timeout=30)
    elif which("lsof"):
        code, out, _ = run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], timeout=40)
    else:
        return None
    if code != 0:
        return None
    for line in (out or "").splitlines()[1:]:
        parts = line.split()
        if len(parts) < 5:
            continue
        proto = parts[0].lower()
        if not proto.startswith(("tcp", "udp")):
            continue
        address = next((p for p in parts if ":" in p and not p.startswith("users")), None)
        if not address:
            continue
        try:
            port = int(address.rsplit(":", 1)[1])
        except ValueError:
            continue
        process = None
        match = re.search(r'users:\(\("([^"]+)"', line)
        if match:
            process = match.group(1)
        ports.append({"proto": proto[:3], "port": port, "process": process})
    unique = {}
    for entry in ports:
        unique[(entry["proto"], entry["port"])] = entry
    return list(unique.values())


def network_addresses():
    ips, macs = [], []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            address = info[4][0]
            if address not in ips and not address.startswith("127.") and address != "::1":
                ips.append(address)
    except OSError:
        pass
    if not ips:
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.settimeout(0.2)
            probe.connect(("192.0.2.1", 9))  # TEST-NET-1: no traffic is sent
            ips.append(probe.getsockname()[0])
            probe.close()
        except OSError:
            pass
    if PLATFORM == "linux" and os.path.isdir("/sys/class/net"):
        for name in sorted(os.listdir("/sys/class/net")):
            if name == "lo":
                continue
            address = read_text("/sys/class/net/{0}/address".format(name), 32)
            if address and address.strip() not in macs:
                macs.append(address.strip())
    else:
        code, out, _ = run(["ifconfig"] if PLATFORM == "macos" else ["ip", "link"], timeout=20)
        for match in re.finditer(r"(?:ether|link/ether)\s+([0-9a-f:]{17})", out or ""):
            if match.group(1) not in macs:
                macs.append(match.group(1))
    return ips, macs


def logged_in_users():
    if PLATFORM == "windows":
        code, out, _ = run(["query", "user"], timeout=20)
        names = []
        for line in (out or "").splitlines()[1:]:
            parts = line.split()
            if parts:
                names.append(parts[0].lstrip(">"))
        return names
    code, out, _ = run(["who"], timeout=20)
    return sorted({line.split()[0] for line in (out or "").splitlines() if line.split()})


def collect_inventory():
    users = local_users() or []
    return {
        "local_users": [{"name": u["name"], "enabled": u.get("enabled", True),
                         "admin": u.get("admin", False),
                         "last_logon": u.get("last_logon_days")} for u in users],
        "software": installed_software()[:500],
        "listening_ports": listening_ports() or [],
        "services": running_services(),
    }


def running_services():
    services = []
    if PLATFORM == "windows":
        code, out, _ = powershell(
            "try{ Get-Service | Select-Object @{n='name';e={$_.Name}},"
            "@{n='state';e={$_.Status.ToString().ToLower()}} | ConvertTo-Json -Compress }"
            "catch{ '' }",
            timeout=60,
        )
        if out and out.strip().startswith(("[", "{")):
            try:
                data = json.loads(out)
                return data if isinstance(data, list) else [data]
            except ValueError:
                return []
        return []
    if which("systemctl"):
        code, out, _ = run(["systemctl", "list-units", "--type=service", "--no-pager",
                            "--no-legend", "--plain"], timeout=45)
        for line in (out or "").splitlines():
            parts = line.split()
            if len(parts) >= 4:
                services.append({"name": parts[0].replace(".service", ""),
                                 "state": "running" if parts[3] == "running" else parts[3]})
    elif PLATFORM == "macos":
        code, out, _ = run(["launchctl", "list"], timeout=30)
        for line in (out or "").splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) >= 3:
                services.append({"name": parts[2],
                                 "state": "running" if parts[0].strip("-").isdigit() else "stopped"})
    return services[:400]


# --------------------------------------------------------------------------------------------
# Report assembly and transport
# --------------------------------------------------------------------------------------------
def checks_for_platform(target=None):
    target = target or PLATFORM
    return [entry for entry in _registry if target in entry["platforms"]]


def run_checks(only=None, verbose=False):
    results = []
    for entry in checks_for_platform():
        if only and entry["id"] != only:
            continue
        if verbose:
            sys.stderr.write("running {0}\n".format(entry["id"]))
        try:
            outcome = entry["func"]()
        except Exception as exc:  # a broken probe must never stop the collection
            outcome = result(ERROR, "", error="{0}: {1}".format(type(exc).__name__, exc))
        outcome = dict(outcome)
        outcome["check_id"] = entry["id"]
        results.append(outcome)
    return results


def build_report(only=None, verbose=False, include_inventory=True):
    ips, macs = network_addresses()
    checks = run_checks(only=only, verbose=verbose)
    try:
        fqdn = socket.getfqdn()
    except OSError:
        fqdn = None
    return {
        "schema_version": SCHEMA_VERSION,
        "agent": {"name": "bulwark-agent", "version": __version__, "platform": PLATFORM},
        "asset": {
            "hostname": socket.gethostname(),
            "fqdn": fqdn,
            "os_family": PLATFORM,
            "os_name": os_name(),
            "os_version": platform.release(),
            "arch": platform.machine(),
            "domain": os.environ.get("USERDOMAIN") or os.environ.get("DOMAIN"),
            "serial_number": serial_number(),
            "ip_addresses": ips,
            "mac_addresses": macs,
            "logged_in_users": logged_in_users(),
        },
        "collected_at": utcnow_iso(),
        "checks": checks,
        "inventory": collect_inventory() if include_inventory else {},
    }


def serial_number():
    if PLATFORM == "windows":
        code, out, _ = powershell("try{ (Get-CimInstance Win32_BIOS).SerialNumber }catch{ '' }",
                                  timeout=30)
        return (out or "").strip() or None
    if PLATFORM == "macos":
        code, out, _ = run(["system_profiler", "SPHardwareDataType"], timeout=45)
        match = re.search(r"Serial Number.*?:\s*(\S+)", out or "")
        return match.group(1) if match else None
    for path in ("/sys/class/dmi/id/product_serial", "/sys/class/dmi/id/board_serial"):
        value = read_text(path, 128)
        if value and value.strip() and "None" not in value:
            return value.strip()
    return None


def load_config():
    for path in CONFIG_PATHS:
        if os.path.isfile(path):
            try:
                with open(path) as handle:
                    return json.load(handle), path
            except (OSError, ValueError):
                continue
    return {}, None


def send(server, key, report, timeout=60, insecure=False):
    """POST the report; returns the decoded response. Raises urllib errors on failure."""
    url = server.rstrip("/") + "/api/agents/report"
    body = json.dumps(report).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
            "User-Agent": "bulwark-agent/" + __version__,
        },
        method="POST",
    )
    context = None
    if insecure:
        import ssl

        context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


# --------------------------------------------------------------------------------------------
# Scheduling
# --------------------------------------------------------------------------------------------
def schedule_command(server, key, insecure):
    script = os.path.abspath(__file__)
    command = [sys.executable, script, "--server", server, "--key", key]
    if insecure:
        command.append("--insecure")
    return command


def install_schedule(server, key, insecure=False):
    """Install a daily run at a host-derived minute so endpoints do not report in lockstep."""
    minute = abs(hash(socket.gethostname())) % 60
    command = " ".join(schedule_command(server, key, insecure))
    if PLATFORM == "linux":
        path = "/etc/cron.d/bulwark-agent"
        line = "{0} 3 * * * root {1} >/dev/null 2>&1\n".format(minute, command)
        try:
            with open(path, "w") as handle:
                handle.write("# Bulwark evidence collection\n" + line)
            os.chmod(path, 0o644)
            return "Installed {0} (daily at 03:{1:02d})".format(path, minute)
        except OSError as exc:
            return "Could not write {0}: {1} (run as root)".format(path, exc)
    if PLATFORM == "macos":
        path = "/Library/LaunchDaemons/com.bulwark.agent.plist"
        arguments = "".join("        <string>{0}</string>\n".format(part)
                            for part in schedule_command(server, key, insecure))
        plist = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0"><dict>\n'
            "    <key>Label</key><string>com.bulwark.agent</string>\n"
            "    <key>ProgramArguments</key><array>\n" + arguments + "    </array>\n"
            "    <key>StartCalendarInterval</key><dict>\n"
            "        <key>Hour</key><integer>3</integer>\n"
            "        <key>Minute</key><integer>{0}</integer>\n".format(minute) +
            "    </dict>\n</dict></plist>\n"
        )
        try:
            with open(path, "w") as handle:
                handle.write(plist)
            os.chmod(path, 0o644)
            run(["launchctl", "load", "-w", path], timeout=20)
            return "Installed {0} (daily at 03:{1:02d})".format(path, minute)
        except OSError as exc:
            return "Could not write {0}: {1} (run with sudo)".format(path, exc)
    quoted = '"{0}" "{1}" --server "{2}" --key "{3}"{4}'.format(
        sys.executable, os.path.abspath(__file__), server, key,
        " --insecure" if insecure else "")
    code, out, err = run(
        ["schtasks", "/Create", "/TN", "Bulwark Agent", "/TR", quoted, "/SC", "DAILY",
         "/ST", "03:{0:02d}".format(minute), "/RU", "SYSTEM", "/RL", "HIGHEST", "/F"],
        timeout=45,
    )
    return out.strip() if code == 0 else "Could not create the scheduled task: {0}".format(
        err.strip() or out.strip())


def uninstall_schedule():
    if PLATFORM == "linux":
        try:
            os.remove("/etc/cron.d/bulwark-agent")
            return "Removed /etc/cron.d/bulwark-agent"
        except OSError as exc:
            return "Could not remove the cron entry: {0}".format(exc)
    if PLATFORM == "macos":
        path = "/Library/LaunchDaemons/com.bulwark.agent.plist"
        run(["launchctl", "unload", "-w", path], timeout=20)
        try:
            os.remove(path)
            return "Removed " + path
        except OSError as exc:
            return "Could not remove the launch daemon: {0}".format(exc)
    code, out, err = run(["schtasks", "/Delete", "/TN", "Bulwark Agent", "/F"], timeout=30)
    return out.strip() if code == 0 else "Could not delete the scheduled task: {0}".format(err)


# --------------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(
        prog="bulwark_agent.py",
        description="Collect CMMC Level 2 configuration evidence and send it to a Bulwark server.",
    )
    parser.add_argument("--server", help="Bulwark server URL, e.g. https://bulwark.example")
    parser.add_argument("--key", help="System enrollment key")
    parser.add_argument("--output", metavar="FILE", help="Write the report to a file instead of sending")
    parser.add_argument("--dry-run", action="store_true", help="Print the report without sending")
    parser.add_argument("--list-checks", action="store_true", help="List the checks for this platform")
    parser.add_argument("--check", metavar="ID", help="Run a single check")
    parser.add_argument("--no-inventory", action="store_true", help="Skip software and port inventory")
    parser.add_argument("--insecure", action="store_true", help="Skip TLS verification (not recommended)")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout in seconds")
    parser.add_argument("--verbose", action="store_true", help="Log each check to stderr")
    parser.add_argument("--install-schedule", action="store_true", help="Install a daily scheduled run")
    parser.add_argument("--uninstall-schedule", action="store_true", help="Remove the scheduled run")
    parser.add_argument("--version", action="version", version="bulwark-agent " + __version__)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.list_checks:
        for entry in sorted(checks_for_platform(), key=lambda e: e["id"]):
            print(entry["id"])
        return 0

    config, config_path = load_config()
    server = args.server or config.get("server")
    key = args.key or config.get("key")
    insecure = args.insecure or bool(config.get("insecure"))

    if args.uninstall_schedule:
        print(uninstall_schedule())
        return 0

    if args.install_schedule:
        if not server or not key:
            sys.stderr.write("--install-schedule needs --server and --key\n")
            return 3
        directory = os.path.dirname(CONFIG_PATHS[0] if PLATFORM != "windows" else CONFIG_PATHS[2])
        try:
            if not os.path.isdir(directory):
                os.makedirs(directory, 0o700)
            path = CONFIG_PATHS[0] if PLATFORM != "windows" else CONFIG_PATHS[2]
            with open(path, "w") as handle:
                json.dump({"server": server, "key": key, "insecure": insecure}, handle)
            os.chmod(path, 0o600)
        except OSError as exc:
            sys.stderr.write("Could not write the agent configuration: {0}\n".format(exc))
        print(install_schedule(server, key, insecure))
        return 0

    if args.check and not any(e["id"] == args.check for e in checks_for_platform()):
        sys.stderr.write("Unknown check for this platform: {0}\n".format(args.check))
        return 3

    report = build_report(only=args.check, verbose=args.verbose,
                          include_inventory=not args.no_inventory)
    counts = {}
    for item in report["checks"]:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    summary = ", ".join("{0} {1}".format(value, name) for name, value in sorted(counts.items()))

    if args.output:
        try:
            with open(args.output, "w") as handle:
                json.dump(report, handle, indent=1)
        except OSError as exc:
            sys.stderr.write("Could not write {0}: {1}\n".format(args.output, exc))
            return 2
        print("Wrote {0} ({1} checks: {2})".format(args.output, len(report["checks"]), summary))
        return 0

    if args.dry_run or not (server and key):
        if not args.dry_run:
            sys.stderr.write("No server or key configured; printing the report instead.\n")
            if config_path:
                sys.stderr.write("Configuration read from {0}\n".format(config_path))
        json.dump(report, sys.stdout, indent=1)
        sys.stdout.write("\n")
        sys.stderr.write("{0} checks: {1}\n".format(len(report["checks"]), summary))
        return 0 if args.dry_run else 3

    if insecure:
        sys.stderr.write("WARNING: TLS certificate verification is disabled.\n")
    try:
        response = send(server, key, report, timeout=args.timeout, insecure=insecure)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        sys.stderr.write("Server rejected the report ({0}): {1}\n".format(exc.code, detail))
        return 2
    except (urllib.error.URLError, OSError, ValueError) as exc:
        sys.stderr.write("Could not reach {0}: {1}\n".format(server, exc))
        return 2
    print(response.get("message") or "Report accepted")
    if response.get("findings"):
        print("{0} failing check(s) recorded as findings".format(response["findings"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
