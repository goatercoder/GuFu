"""Static checks on the Windows agent.

PowerShell is not available in this project's CI, so the script cannot be executed here. These
tests enforce the properties that would otherwise be caught at runtime: it parses, it covers the
catalog, and it avoids constructs Windows PowerShell 5.1 cannot run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

AGENT = Path(__file__).resolve().parents[1] / "Bulwark-Agent.ps1"
CATALOG = Path(__file__).resolve().parents[2] / "catalog" / "checks.json"


@pytest.fixture(scope="module")
def source() -> str:
    return AGENT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code_lines(source: str) -> list[str]:
    """Source lines with comments, here-strings and quoted strings blanked out."""
    lines = source.split("\n")
    out: list[str] = []
    in_block_comment = False
    in_here_string = False
    for line in lines:
        if in_here_string:
            if re.match(r"^\s*['\"]@", line):
                in_here_string = False
            out.append("")
            continue
        if in_block_comment:
            if "#>" in line:
                in_block_comment = False
                line = line.split("#>", 1)[1]
            else:
                out.append("")
                continue
        if "<#" in line:
            before = line.split("<#", 1)[0]
            if "#>" in line.split("<#", 1)[1]:
                line = before + line.split("#>", 1)[1]
            else:
                in_block_comment = True
                out.append(before)
                continue
        if re.search(r"@['\"]\s*$", line):
            in_here_string = True
            out.append(re.sub(r"@['\"]\s*$", "", line))
            continue
        # Blank out quoted strings, honouring PowerShell's doubled-quote escapes.
        stripped = re.sub(r"'(?:[^']|'')*'", "''", line)
        stripped = re.sub(r'"(?:[^"`]|`.)*"', '""', stripped)
        stripped = stripped.split("#", 1)[0] if not stripped.strip().startswith("#") else ""
        out.append(stripped)
    return out


def test_the_script_exists_and_declares_its_version(source):
    assert source.startswith("<#")
    assert "$AgentVersion = '0.1.0'" in source
    assert "Set-StrictMode -Version 2" in source


def test_brackets_balance(code_lines):
    pairs = {"{": "}", "(": ")", "[": "]"}
    closers = {v: k for k, v in pairs.items()}
    stack: list[tuple[str, int]] = []
    for number, line in enumerate(code_lines, start=1):
        for char in line:
            if char in pairs:
                stack.append((char, number))
            elif char in closers:
                assert stack, f"unmatched {char} on line {number}"
                opener, opened = stack.pop()
                assert opener == closers[char], (
                    f"{char} on line {number} closes {opener} opened on line {opened}"
                )
    assert not stack, f"unclosed {stack[-1][0]} from line {stack[-1][1]}"


def test_quotes_balance_on_every_line(code_lines, source):
    """After blanking strings, no stray quote characters should remain."""
    for number, line in enumerate(code_lines, start=1):
        assert line.count("'") % 2 == 0, f"odd single quote on line {number}: {line}"


@pytest.mark.parametrize(
    ("pattern", "reason"),
    [
        (r"\?\?", "the null-coalescing operator needs PowerShell 7"),
        (r"\s\?\s.+\s:\s", "the ternary operator needs PowerShell 7"),
        (r"-Parallel", "ForEach-Object -Parallel needs PowerShell 7"),
        (r"Win32_Product", "querying Win32_Product reconfigures every installed package"),
        (r"(?m)^\s*class\s+\w+", "PowerShell classes parse differently on 5.1"),
        (r"Invoke-WebRequest\s+-SkipCertificateCheck", "-SkipCertificateCheck needs PowerShell 6+"),
    ],
)
def test_no_incompatible_constructs(code_lines, pattern, reason):
    for number, line in enumerate(code_lines, start=1):
        assert not re.search(pattern, line), f"line {number}: {reason}\n{line}"


def test_registered_checks_match_the_catalog(source):
    with CATALOG.open() as handle:
        catalog = json.load(handle)["checks"]
    expected = {c["id"] for c in catalog if "windows" in c["platforms"]}
    registered = set(re.findall(r"Register-Check\s+'([^']+)'", source))
    assert registered == expected, {
        "missing": sorted(expected - registered),
        "extra": sorted(registered - expected),
    }


def test_thresholds_match_the_catalog(source):
    with CATALOG.open() as handle:
        catalog = json.load(handle)["checks"]
    block = source.split("$Params = @{", 1)[1].split("\n}", 1)[0]
    for check in catalog:
        params = check.get("params") or {}
        if not params or "windows" not in check["platforms"]:
            continue
        line = next((ln for ln in block.split("\n") if f"'{check['id']}'" in ln), None)
        assert line, f"{check['id']} has no threshold entry"
        for name, value in params.items():
            assert f"{name} = {value}" in line, f"{check['id']}: {name} should be {value}"


def test_every_called_helper_is_defined(source, code_lines):
    defined = set(re.findall(r"(?m)^function\s+([A-Za-z]+-[A-Za-z]+)", source))
    called = set()
    for line in code_lines:
        for name in re.findall(r"\b([A-Z][a-z]+-[A-Za-z]+)\b", line):
            called.add(name)
    builtin_prefixes = (
        "Get-", "Set-", "New-", "Write-", "Test-", "Join-", "Split-", "Remove-", "Select-",
        "Sort-", "Where-", "ForEach-", "ConvertTo-", "ConvertFrom-", "Invoke-", "Confirm-",
        "Out-", "Start-", "Stop-", "Add-", "Import-", "Export-", "Measure-",
    )
    project_calls = {
        name for name in called
        if name in defined or not name.startswith(builtin_prefixes)
    }
    undefined = {name for name in project_calls if name not in defined}
    assert not undefined, f"called but not defined: {sorted(undefined)}"


def test_defined_helpers_are_used(source, code_lines):
    defined = set(re.findall(r"(?m)^function\s+([A-Za-z]+-[A-Za-z]+)", source))
    body = "\n".join(code_lines)
    for name in defined:
        uses = len(re.findall(rf"\b{re.escape(name)}\b", body))
        assert uses >= 2, f"{name} is defined but never called"


def test_every_check_returns_a_result(source):
    """Each Register-Check body must produce a result object on every path."""
    blocks = re.findall(r"Register-Check\s+'([^']+)'\s*\{(.*?)\n\}\n", source, re.S)
    assert len(blocks) >= 30
    for check_id, body in blocks:
        assert "New-Result" in body or "New-ErrorResult" in body, check_id


def test_secrets_are_never_written_to_output(code_lines):
    """The key may be passed to a function, but never emitted to the console or a log."""
    for number, line in enumerate(code_lines, start=1):
        if not re.search(r"Write-(Output|Host|Verbose|Warning|Error)", line):
            continue
        # Drop '-ParameterName $Key' argument passing; what is left would be printed.
        printed = re.sub(r"-\w+\s*:?\s*\$(Key|EnrollmentKey)\b", "", line)
        assert "$Key" not in printed, f"line {number} would print the enrollment key: {line}"
        assert "$EnrollmentKey" not in printed, f"line {number} would print the enrollment key"


def test_the_key_is_sent_as_a_bearer_header(source):
    assert "Authorization = ('Bearer ' + $EnrollmentKey)" in source
    assert "[Net.SecurityProtocolType]::Tls12" in source


def test_exit_codes_follow_the_python_agent(source):
    assert "exit 2" in source  # transport failure
    assert "exit 3" in source  # bad arguments


def test_scheduled_task_runs_as_system_daily(source):
    assert "/SC DAILY" in source
    assert "/RU SYSTEM" in source
    assert "schtasks.exe /Delete /TN 'Bulwark Agent' /F" in source
