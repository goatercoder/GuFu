"""Agent behaviour: check coverage, report shape, parsing and transport."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import bulwark_agent as agent

CATALOG = Path(__file__).resolve().parents[2] / "catalog" / "checks.json"
AGENT_PATH = Path(agent.__file__)


@pytest.fixture(scope="module")
def catalog_checks() -> list[dict]:
    with CATALOG.open() as handle:
        return json.load(handle)["checks"]


# --------------------------------------------------------------------------------------------
# Coverage of the catalog
# --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("platform", ["windows", "linux", "macos"])
def test_every_catalog_check_is_implemented(catalog_checks, platform):
    expected = {c["id"] for c in catalog_checks if platform in c["platforms"]}
    implemented = {entry["id"] for entry in agent.checks_for_platform(platform)}
    assert implemented == expected, {
        "missing": sorted(expected - implemented),
        "extra": sorted(implemented - expected),
    }


def test_thresholds_match_the_catalog(catalog_checks):
    for check in catalog_checks:
        params = check.get("params") or {}
        if not params:
            continue
        assert agent.PARAMS.get(check["id"]) == params, check["id"]


# --------------------------------------------------------------------------------------------
# Report shape (ARCHITECTURE.md §3)
# --------------------------------------------------------------------------------------------
VALID_STATUSES = {"pass", "fail", "error", "not_applicable", "info"}


def validate_report(report: dict) -> None:
    assert report["schema_version"] == 1
    assert report["agent"]["name"] == "bulwark-agent"
    assert report["agent"]["platform"] in {"windows", "linux", "macos"}
    asset = report["asset"]
    assert asset["hostname"]
    for field in ("fqdn", "os_family", "os_name", "os_version", "arch", "domain", "serial_number"):
        assert field in asset
    for field in ("ip_addresses", "mac_addresses", "logged_in_users"):
        assert isinstance(asset[field], list)
    assert report["collected_at"].endswith("Z")
    assert isinstance(report["checks"], list) and report["checks"]
    for item in report["checks"]:
        assert item["check_id"]
        assert item["status"] in VALID_STATUSES
        assert "observed" in item and "expected" in item
        assert "details" in item and "error" in item
        if item["status"] == "error":
            assert item["error"]


def test_report_matches_the_server_schema():
    validate_report(agent.build_report(include_inventory=False))


def test_report_includes_inventory_when_asked():
    report = agent.build_report(include_inventory=True)
    inventory = report["inventory"]
    for field in ("local_users", "software", "listening_ports", "services"):
        assert field in inventory
        assert isinstance(inventory[field], list)


def test_running_a_single_check_returns_only_that_check():
    report = agent.build_report(only="os.firewall.enabled", include_inventory=False)
    assert [c["check_id"] for c in report["checks"]] == ["os.firewall.enabled"]


def test_a_real_run_produces_useful_results():
    """Every check must return something an assessor can read, not a crash."""
    results = agent.run_checks()
    assert len(results) >= 25
    for item in results:
        assert item["status"] in VALID_STATUSES
        assert item["observed"] or item["error"], item["check_id"]
    statuses = {item["status"] for item in results}
    assert "pass" in statuses


def test_a_raising_check_is_reported_as_an_error(monkeypatch):
    def explode():
        raise RuntimeError("probe blew up")

    monkeypatch.setattr(agent, "_registry",
                        [{"id": "test.boom", "platforms": (agent.PLATFORM,), "func": explode}])
    results = agent.run_checks()
    assert results[0]["status"] == "error"
    assert "probe blew up" in results[0]["error"]


def test_run_never_raises_when_a_command_is_missing(monkeypatch):
    monkeypatch.setattr(agent.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    code, out, err = agent.run(["definitely-not-a-command"])
    assert code == 127 and err == "command not found"


def test_run_reports_a_timeout(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(agent.subprocess, "run", timeout)
    code, _, err = agent.run(["sleep"])
    assert code == 124 and err == "timed out"


# --------------------------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------------------------
def test_password_policy_parsing_from_pwquality(monkeypatch, tmp_path):
    conf = tmp_path / "pwquality.conf"
    conf.write_text("minlen = 16\nminclass = 4\ndcredit = -1\n")
    logindefs = tmp_path / "login.defs"
    logindefs.write_text("PASS_MIN_LEN 8\n")
    monkeypatch.setattr(agent, "read_text",
                        lambda path, limit=200000: {
                            "/etc/security/pwquality.conf": conf.read_text(),
                            "/etc/login.defs": logindefs.read_text(),
                        }.get(path))
    values = agent.linux_pwquality()
    assert values["minlen"] == "16"
    assert values["minclass"] == "4"


def test_faillock_threshold_parsing(monkeypatch):
    monkeypatch.setattr(agent, "PLATFORM", "linux")
    monkeypatch.setattr(agent, "linux_pwquality", lambda: {"deny": "5"})
    outcome = agent.check_lockout()
    assert outcome["status"] == "pass"
    assert "5" in outcome["observed"]

    monkeypatch.setattr(agent, "linux_pwquality", lambda: {"deny": "25"})
    assert agent.check_lockout()["status"] == "fail"

    monkeypatch.setattr(agent, "linux_pwquality", lambda: {})
    monkeypatch.setattr(agent, "read_text", lambda *a, **k: "")
    assert agent.check_lockout()["status"] == "fail"


UFW_ACTIVE = """Status: active
Logging: on (low)
Default: deny (incoming), allow (outgoing), disabled (routed)
New profiles: skip
"""

FIREWALLD_RUNNING = "running\n"


def test_ufw_state_parsing(monkeypatch):
    monkeypatch.setattr(agent, "which", lambda name: "/usr/sbin/ufw" if name == "ufw" else None)
    monkeypatch.setattr(agent, "run", lambda *a, **k: (0, UFW_ACTIVE, ""))
    name, active, inbound, _ = agent.linux_firewall_state()
    assert (name, active, inbound) == ("ufw", True, "deny")


def test_firewalld_state_parsing(monkeypatch):
    monkeypatch.setattr(agent, "which", lambda name: "/usr/bin/firewall-cmd"
                        if name == "firewall-cmd" else None)
    calls = {"n": 0}

    def fake_run(command, **kwargs):
        calls["n"] += 1
        if "--state" in command:
            return 0, FIREWALLD_RUNNING, ""
        return 0, "public\n", ""

    monkeypatch.setattr(agent, "run", fake_run)
    name, active, inbound, _ = agent.linux_firewall_state()
    assert (name, active, inbound) == ("firewalld", True, "allow")


def test_iptables_drop_policy_is_default_deny(monkeypatch):
    monkeypatch.setattr(agent, "which", lambda name: "/sbin/iptables" if name == "iptables" else None)
    monkeypatch.setattr(agent, "run", lambda *a, **k: (0, "-P INPUT DROP\n-A INPUT -p tcp -j ACCEPT\n", ""))
    name, active, inbound, _ = agent.linux_firewall_state()
    assert (name, active, inbound) == ("iptables", True, "deny")


TIMEDATECTL = "NTP=yes\nNTPSynchronized=yes\nTimezone=UTC\n"


def test_time_sync_parsing(monkeypatch):
    monkeypatch.setattr(agent, "PLATFORM", "linux")
    monkeypatch.setattr(agent, "run", lambda *a, **k: (0, TIMEDATECTL, ""))
    assert agent.check_time_sync()["status"] == "pass"
    monkeypatch.setattr(agent, "run", lambda *a, **k: (0, "NTP=no\nNTPSynchronized=no\n", ""))
    assert agent.check_time_sync()["status"] == "fail"


SSHD_T = """port 22
permitrootlogin no
passwordauthentication no
clientaliveinterval 300
clientalivecountmax 2
banner /etc/issue.net
"""


def test_sshd_config_parsing(monkeypatch, tmp_path):
    sshd = tmp_path / "sshd"
    sshd.write_text("")
    monkeypatch.setattr(agent.os.path, "exists", lambda path: str(path) == str(sshd))
    monkeypatch.setattr(agent, "which", lambda name: str(sshd) if name == "sshd" else None)
    monkeypatch.setattr(agent, "run", lambda *a, **k: (0, SSHD_T, ""))
    values = agent.sshd_config()
    assert values["permitrootlogin"] == "no"
    assert values["clientaliveinterval"] == "300"


def test_hardened_ssh_passes_remote_access(monkeypatch):
    monkeypatch.setattr(agent, "PLATFORM", "linux")
    monkeypatch.setattr(agent, "sshd_config", lambda: {
        "permitrootlogin": "no", "passwordauthentication": "no"})
    monkeypatch.setattr(agent, "run", lambda *a, **k: (0, "1234", ""))  # pgrep finds sshd
    assert agent.check_remote_access()["status"] == "pass"

    monkeypatch.setattr(agent, "sshd_config", lambda: {
        "permitrootlogin": "yes", "passwordauthentication": "yes"})
    assert agent.check_remote_access()["status"] == "fail"


def test_disk_encryption_detects_a_luks_volume(monkeypatch):
    monkeypatch.setattr(agent, "PLATFORM", "linux")
    monkeypatch.setattr(agent, "run", lambda *a, **k: (
        0, "NAME TYPE MOUNTPOINT\nsda disk\nsda3 crypt /\n", ""))
    assert agent.check_disk_encryption()["status"] == "pass"
    monkeypatch.setattr(agent, "run", lambda *a, **k: (0, "NAME TYPE MOUNTPOINT\nsda disk\n", ""))
    assert agent.check_disk_encryption()["status"] == "fail"


def test_pending_updates_from_apt(monkeypatch):
    monkeypatch.setattr(agent, "PLATFORM", "linux")
    monkeypatch.setattr(agent, "which", lambda name: "/usr/bin/apt-get" if name == "apt-get" else None)
    monkeypatch.setattr(agent, "run", lambda *a, **k: (
        0, "Inst libc6 [2.1] (2.2 security)\n3 upgraded, 0 newly installed, 0 to remove\n", ""))
    outcome = agent.check_pending_updates()
    assert outcome["status"] == "fail"
    assert "3 package(s) upgradable" in outcome["observed"]

    monkeypatch.setattr(agent, "run", lambda *a, **k: (
        0, "0 upgraded, 0 newly installed, 0 to remove\n", ""))
    assert agent.check_pending_updates()["status"] == "pass"


def test_pending_updates_from_dnf_return_code(monkeypatch):
    monkeypatch.setattr(agent, "PLATFORM", "linux")
    monkeypatch.setattr(agent, "which", lambda name: "/usr/bin/dnf" if name == "dnf" else None)
    monkeypatch.setattr(agent, "run", lambda *a, **k: (100, "kernel.x86_64 6.1\nopenssl.x86_64 3.0\n", ""))
    outcome = agent.check_pending_updates()
    assert outcome["status"] == "fail"
    assert "2 package update(s)" in outcome["observed"]


def test_end_of_life_linux_release_fails(monkeypatch):
    monkeypatch.setattr(agent, "PLATFORM", "linux")
    monkeypatch.setattr(agent, "read_text",
                        lambda *a, **k: 'PRETTY_NAME="Ubuntu 18.04.6 LTS"\n')
    assert agent.check_os_supported()["status"] == "fail"
    monkeypatch.setattr(agent, "read_text",
                        lambda *a, **k: 'PRETTY_NAME="Ubuntu 24.04.4 LTS"\n')
    assert agent.check_os_supported()["status"] == "pass"


def test_screen_lock_is_not_applicable_without_a_desktop(monkeypatch):
    monkeypatch.setattr(agent, "PLATFORM", "linux")
    monkeypatch.setattr(agent, "has_graphical_session", lambda: False)
    outcome = agent.check_screen_lock()
    assert outcome["status"] == "not_applicable"
    assert "no screen to lock" in outcome["observed"]


def test_locked_password_does_not_hide_an_admin_account(monkeypatch):
    """An account with a login shell is usable with a key even if its password is locked."""
    monkeypatch.setattr(agent, "PLATFORM", "linux")
    files = {
        "/etc/passwd": "root:x:0:0::/root:/bin/bash\n"
                       "svc:x:999:999::/:/usr/sbin/nologin\n"
                       "joe:x:1000:1000::/home/joe:/bin/bash\n",
        "/etc/group": "sudo:x:27:joe\n",
        "/etc/shadow": "root:!:19000:0:99999:7:::\njoe:$6$abc:19000:0:99999:7:::\n",
    }
    monkeypatch.setattr(agent, "read_text", lambda path, limit=200000: files.get(path))
    monkeypatch.setattr(agent, "run", lambda *a, **k: (1, "", ""))
    users = {u["name"]: u for u in agent.local_users()}
    assert users["root"]["admin"] is True and users["root"]["enabled"] is True
    assert users["root"]["password_locked"] is True
    assert users["svc"]["enabled"] is False
    assert users["joe"]["admin"] is True


# --------------------------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------------------------
def test_send_sets_the_authorization_header(monkeypatch):
    captured = {}

    class FakeResponse:
        def read(self):
            return b'{"ok": true, "message": "stored"}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout=None, context=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode())
        return FakeResponse()

    monkeypatch.setattr(agent.urllib.request, "urlopen", fake_urlopen)
    response = agent.send("https://bulwark.example/", "secret-key", {"schema_version": 1})
    assert response["ok"] is True
    assert captured["url"] == "https://bulwark.example/api/agents/report"
    assert captured["headers"]["Authorization"] == "Bearer secret-key"
    assert captured["headers"]["Content-type"] == "application/json"


def test_transport_failure_exits_with_code_two(monkeypatch):
    monkeypatch.setattr(agent, "build_report", lambda **kwargs: {"schema_version": 1, "checks": []})
    monkeypatch.setattr(agent, "load_config", lambda: ({}, None))

    def fail(*args, **kwargs):
        raise agent.urllib.error.URLError("connection refused")

    monkeypatch.setattr(agent, "send", fail)
    assert agent.main(["--server", "https://x.example", "--key", "k"]) == 2


def test_unknown_check_exits_with_code_three():
    assert agent.main(["--check", "no.such.check", "--dry-run"]) == 3


# --------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------
def test_output_writes_a_valid_report(tmp_path):
    destination = tmp_path / "report.json"
    assert agent.main(["--output", str(destination), "--no-inventory"]) == 0
    validate_report(json.loads(destination.read_text()))


def test_list_checks_prints_the_platform_set(capsys):
    assert agent.main(["--list-checks"]) == 0
    printed = {line for line in capsys.readouterr().out.splitlines() if line}
    assert printed == {entry["id"] for entry in agent.checks_for_platform()}


def test_dry_run_prints_json_to_stdout():
    completed = subprocess.run(
        [sys.executable, str(AGENT_PATH), "--dry-run", "--no-inventory",
         "--check", "os.firewall.enabled"],
        capture_output=True, timeout=180,
    )
    assert completed.returncode == 0
    validate_report(json.loads(completed.stdout.decode()))


def test_the_key_is_never_printed(capsys, monkeypatch):
    monkeypatch.setattr(agent, "build_report", lambda **kwargs: {"schema_version": 1, "checks": []})
    monkeypatch.setattr(agent, "send", lambda *a, **k: {"message": "ok", "findings": 0})
    agent.main(["--server", "https://x.example", "--key", "super-secret-key"])
    captured = capsys.readouterr()
    assert "super-secret-key" not in captured.out
    assert "super-secret-key" not in captured.err


def test_config_file_supplies_the_server_and_key(tmp_path, monkeypatch):
    config = tmp_path / "agent.json"
    config.write_text(json.dumps({"server": "https://cfg.example", "key": "cfg-key"}))
    monkeypatch.setattr(agent, "CONFIG_PATHS", [str(config)])
    loaded, path = agent.load_config()
    assert loaded["server"] == "https://cfg.example"
    assert path == str(config)
