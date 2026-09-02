"""
safety.py — Three-tier safety evaluation system.

Levels:
    SAFE        (0) — read-only / navigation, runs immediately or with [Y/n]
    SUSPICIOUS  (1) — mutates state / executes code, requires explicit 'YES'
    CRITICAL    (2) — potentially destructive, hard-blocked with no bypass
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class SafetyLevel(IntEnum):
    SAFE = 0
    SUSPICIOUS = 1
    CRITICAL = 2



# POSIX (bash/zsh) — only commands that do NOT mutate system state
POSIX_SAFE = {
    "ls", "dir", "cat", "pwd", "echo", "find", "grep", "egrep", "fgrep",
    "head", "tail", "wc", "sort", "uniq", "less", "more", "file", "stat",
    "whoami", "uname", "date", "env", "printenv", "which", "type", "df",
    "history", "tree", "basename", "dirname", "realpath", "id", "hostname",
}
# git subcommands that don't change anything
GIT_SAFE_SUBCOMMANDS = {
    "status", "log", "diff", "branch", "show", "remote", "fetch",
    "blame", "shortlog", "describe", "rev-parse", "config", "stash",
}
GIT_SUSPICIOUS_SUBCOMMANDS = {
    "push", "commit", "reset", "checkout", "merge", "rebase", "clean",
    "cherry-pick", "revert", "tag",
}

# Mutates files / executes external code — but legitimate in a dev workflow
POSIX_SUSPICIOUS = {
    "python", "python3", "pip", "pip3", "node", "npm", "npx",
    "docker", "docker-compose", "curl", "wget", "ssh", "scp", "rsync",
    "chmod", "chown", "mv", "cp", "mkdir", "touch", "tar", "zip", "unzip",
    "kill", "killall", "systemctl", "service", "crontab", "sed", "awk",
    "sudo", "runas",  # privilege escalation -> handled strictly below
    "rm", "eval", "exec", "source",
}

# PowerShell — cmdlet names are case-insensitive, so compare in lower()
PS_SAFE = {
    "get-location", "gl", "get-childitem", "gci", "dir", "ls",
    "get-content", "gc", "cat", "type", "get-item", "gi",
    "get-process", "gps", "get-date", "write-host", "write-output",
    "echo", "select-string", "sls", "get-history", "clear-host", "cls",
    "get-command", "gcm", "get-help", "get-module", "get-service",
    "test-path", "resolve-path", "get-acl", "pwd",
}
PS_SUSPICIOUS = {
    "invoke-restmethod", "irm", "invoke-webrequest", "iwr",
    "start-process", "new-item", "remove-item", "ri", "copy-item",
    "move-item", "rename-item", "set-content", "sc", "add-content",
    "invoke-expression", "iex", "invoke-command", "icm",
    "set-executionpolicy", "stop-process", "stop-service",
    "start-service", "new-object", "start-job",
}

# CMD.exe
CMD_SAFE = {"dir", "type", "echo", "cd", "cls", "hostname", "ver", "vol", "findstr"}
CMD_SUSPICIOUS = {
    "copy", "move", "xcopy", "robocopy", "reg", "schtasks", "net",
    "sc", "wmic", "attrib", "icacls", "cacls", "taskkill", "runas",
}

# Binaries that are ALWAYS critical, regardless of arguments
ALWAYS_CRITICAL_BINARIES = {
    "format", "diskpart", "mkfs", "fdisk", "bcdedit", "cipher",
    "vssadmin",  # commonly used by ransomware to delete shadow copies
}

# sudo/runas — treated as CRITICAL: if the model generated a command with
# privilege escalation, the entire point of the allow/deny-list sandbox is
# defeated, since everything is permitted under root/administrator.
PRIVILEGE_ESCALATION = {"sudo", "runas", "su"}


@dataclass(frozen=True)
class CriticalPattern:
    regex: re.Pattern
    description: str


CRITICAL_PATTERNS: list[CriticalPattern] = [
    CriticalPattern(
        re.compile(
            r"\brm\s+(?:-[a-zA-Z-]*\s+)*"
            r"(?:-[a-zA-Z]*[rR][a-zA-Z]*[fF][a-zA-Z]*|-[a-zA-Z]*[fF][a-zA-Z]*[rR][a-zA-Z]*|"
            r"--recursive|--force)"
            r"(?:\s+(?:-[a-zA-Z-]+|--\S+))*\s+"
            r"(?:/|/\*|~/?|\$HOME\b|\.\.?/?|\*)(?=$|[\s;&|'\")])"
        ),
        "rm with recursive force-delete of root/home/wildcard",
    ),
    # PowerShell: Remove-Item -Recurse -Force C:\  (flags in any order)
    CriticalPattern(
        re.compile(
            r"(?:remove-item|ri)\b(?=.*-recurse)(?=.*-force)"
            r".*\b([a-zA-Z]:\\?\s*$|\$env:\w+\s*$)",
            re.IGNORECASE,
        ),
        "Remove-Item -Recurse -Force on a drive root",
    ),
    # rd /s /q C:\   (Windows CMD)
    CriticalPattern(
        re.compile(r"\brd\s+(/s\s+/q|/q\s+/s)\s+[a-zA-Z]:\\?\s*$", re.IGNORECASE),
        "rd /s /q on a drive root",
    ),
    CriticalPattern(
        re.compile(
            r"\b(remove-item|ri|rmdir|rd|rm|del)\b[^;&|]*"
            r"(?:-recurse|-r\b|-rf\b|-fr\b|/s\b)[^;&|]*"
            r"(?:[a-zA-Z]:[\\/]?\*?\s*(?:[;&|]|$)|(?<![\w.])/(?:\*)?\s*(?:[;&|]|$)|\$home\b|~\s*(?:[;&|]|$))",
            re.IGNORECASE,
        ),
        "recursive force-delete targeting a drive root/home/wildcard (flags-then-target)",
    ),
    CriticalPattern(
        re.compile(
            r"\b(remove-item|ri|rmdir|rd|rm|del)\b[^;&|]*"
            r"(?:[a-zA-Z]:[\\/]?\*?\s+|(?<![\w.])/(?:\*)?\s+|\$home\b\s+|~\s+)[^;&|]*"
            r"(?:-recurse|-r\b|-rf\b|-fr\b|/s\b)",
            re.IGNORECASE,
        ),
        "recursive force-delete targeting a drive root/home/wildcard (target-then-flags)",
    ),
    # del /f /s /q C:\*
    CriticalPattern(
        re.compile(r"\bdel\s+(/f\s+/s\s+/q|/s\s+/f\s+/q)\s+[a-zA-Z]:\\", re.IGNORECASE),
        "del /f /s /q on a drive",
    ),
    # dd if=... of=/dev/sdX or /dev/nvme..
    CriticalPattern(
        re.compile(r"\bdd\b.*\bof=/dev/(sd|nvme|hd|disk)\w*", re.IGNORECASE),
        "dd writing directly to a block device",
    ),
    # redirecting output straight to a block device: >/dev/sda
    CriticalPattern(
        re.compile(r">\s*/dev/(sd|nvme|hd|disk)\w*"),
        "output redirected to a block device",
    ),
    # fork bomb :(){ :|:& };:
    CriticalPattern(
        re.compile(r":\s*\(\s*\)\s*\{[^}]*:\s*\|\s*:.*\}\s*;\s*:"),
        "fork bomb",
    ),
    # classic PowerShell download-and-execute cradle:
    # IEX (New-Object Net.WebClient).DownloadString('http://...')
    CriticalPattern(
        re.compile(
            r"(?:iex|invoke-expression)[^;&|]*(?:downloadstring|downloadfile)"
            r"|(?:downloadstring|downloadfile)[^;&|]*(?:iex|invoke-expression)",
            re.IGNORECASE,
        ),
        "download-and-execute cradle (DownloadString/File piped into IEX)",
    ),
    # chmod -R 777 /  (opens up permissions on the root filesystem)
    CriticalPattern(
        re.compile(r"\bchmod\s+-R\s+[0-7]{3,4}\s+/\s*(?:[;&|]|$)"),
        "chmod -R on the root filesystem",
    ),
]

SUSPICIOUS_PATTERNS: list[CriticalPattern] = [
    # Invoke-Expression / IEX on downloaded content — classic download cradle
    CriticalPattern(
        re.compile(r"(?:iex|invoke-expression)\s*\(?\s*(?:irm|iwr|invoke-restmethod|invoke-webrequest)", re.IGNORECASE),
        "PowerShell download cradle (IEX on a web request result)",
    ),
    CriticalPattern(
        re.compile(r"curl[^\n|]*\|\s*(?:bash|sh|python3?)\b"),
        "curl | bash — executing an arbitrary remote script",
    ),
    CriticalPattern(
        re.compile(r"while\s*\(\s*\$true\s*\)", re.IGNORECASE),
        "infinite loop (while($true))",
    ),
    CriticalPattern(
        re.compile(r"start-process\s+powershell", re.IGNORECASE),
        "spawns a new PowerShell process",
    ),
    # Downloading remote content is not destructive by itself (no execution
    # implied) — escalated to CRITICAL only when piped into IEX, see above.
    CriticalPattern(
        re.compile(r"downloadstring|downloadfile", re.IGNORECASE),
        ".NET WebClient download (verify what it's used for)",
    ),
]


def split_logical_segments(cmd: str) -> list[str]:
    segments: list[str] = []
    current: list[str] = []
    quote_char: Optional[str] = None
    i, n = 0, len(cmd)

    while i < n:
        ch = cmd[i]

        if quote_char:
            current.append(ch)
            if ch == quote_char and (i == 0 or cmd[i - 1] != "\\"):
                quote_char = None
            i += 1
            continue

        if ch in ("'", '"'):
            quote_char = ch
            current.append(ch)
            i += 1
            continue

        if cmd[i:i + 2] in ("&&", "||"):
            segments.append("".join(current))
            current = []
            i += 2
            continue

        if ch in (";", "&", "|"):
            segments.append("".join(current))
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    if current:
        segments.append("".join(current))

    return [s.strip() for s in segments if s.strip()]


def tokenize_segment(segment: str) -> list[str]:
    for posix_mode in (True, False):
        try:
            return shlex.split(segment, posix=posix_mode)
        except ValueError:
            continue
    return re.findall(r'"[^"]*"|\'[^\']*\'|\S+', segment)


def _dequote(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    return token


def _decode_powershell_b64(payload: str) -> Optional[str]:
    """
    PowerShell's -EncodedCommand expects a Base64 string that decodes to
    UTF-16LE plaintext (that's what `[Convert]::ToBase64String` produces
    from a .NET string). Returns None if the payload isn't valid Base64 or
    doesn't decode to plausible text, so callers can fail-safe on it.
    """
    import base64

    payload = payload.strip()
    if not payload or len(payload) < 8:
        return None
    if not re.fullmatch(r"[A-Za-z0-9+/]+=*", payload):
        return None
    padded = payload + "=" * (-len(payload) % 4)
    try:
        raw = base64.b64decode(padded, validate=True)
        return raw.decode("utf-16-le")
    except Exception:
        try:
            return base64.b64decode(padded, validate=True).decode("utf-8")
        except Exception:
            return None



def _binary_name(token: str) -> str:
    import os
    name = os.path.basename(_dequote(token)).lower()
    if name.endswith(".exe"):
        name = name[:-4]
    if name.endswith(".ps1"):
        name = name[:-4]
    return name


def _classify_segment(segment: str, mode: str) -> tuple[SafetyLevel, str]:
    """mode: 'bash' | 'shell' (PowerShell) | 'cmd'"""
    tokens = tokenize_segment(segment)
    if not tokens:
        return SafetyLevel.SAFE, ""

    binname = _binary_name(tokens[0])
    args = tokens[1:]

    if binname in ALWAYS_CRITICAL_BINARIES:
        return SafetyLevel.CRITICAL, f"Destructive utility: {binname}"
    if binname in PRIVILEGE_ESCALATION:
        return SafetyLevel.CRITICAL, f"Privilege escalation attempt: {binname}"

    if binname == "git" and args:
        sub = args[0].lower()
        if sub in GIT_SAFE_SUBCOMMANDS:
            return SafetyLevel.SAFE, ""
        if sub in GIT_SUSPICIOUS_SUBCOMMANDS:
            return SafetyLevel.SUSPICIOUS, f"git {sub} mutates the repo/history"
        return SafetyLevel.SUSPICIOUS, f"Unknown git subcommand: {sub}"

    if mode == "shell":  # PowerShell
        safe_set, suspicious_set = PS_SAFE, PS_SUSPICIOUS
    elif mode == "cmd":
        safe_set, suspicious_set = CMD_SAFE, CMD_SUSPICIOUS
    else:  # bash / posix
        safe_set, suspicious_set = POSIX_SAFE, POSIX_SUSPICIOUS

    if binname in safe_set:
        return SafetyLevel.SAFE, ""
    if binname in suspicious_set:
        return SafetyLevel.SUSPICIOUS, f"Command mutates state / executes code: {binname}"

    return SafetyLevel.SUSPICIOUS, f"Binary outside whitelist (not confirmed safe): {binname}"



def evaluate_command_safety(
    cmd: str,
    mode: str = "bash",
    _depth: int = 0,
) -> tuple[SafetyLevel, str, str]:
    if not cmd or not cmd.strip():
        return SafetyLevel.SAFE, "", cmd

    highlighted = cmd
    worst_level = SafetyLevel.SAFE
    worst_reason = ""

    def _bump(level: SafetyLevel, reason: str, token: Optional[str] = None):
        nonlocal worst_level, worst_reason, highlighted
        if level > worst_level:
            worst_level, worst_reason = level, reason
            if token and token in highlighted:
                highlighted = highlighted.replace(token, f"[[{token}]]", 1)

    for pat in CRITICAL_PATTERNS:
        m = pat.regex.search(cmd)
        if m:
            _bump(SafetyLevel.CRITICAL, pat.description, m.group(0))

    for pat in SUSPICIOUS_PATTERNS:
        m = pat.regex.search(cmd)
        if m:
            _bump(SafetyLevel.SUSPICIOUS, pat.description, m.group(0))

    if worst_level == SafetyLevel.CRITICAL:
        return worst_level, worst_reason, highlighted

    if _depth < 2:
        eval_flags = ("-c", "-command", "/c", "--eval") if mode == "shell" else ("-c", "--eval")
        for seg in split_logical_segments(cmd):
            toks = tokenize_segment(seg)
            for i, tok in enumerate(toks[:-1]):
                if tok.lower() in eval_flags:
                    inner = _dequote(toks[i + 1])
                    if inner.strip():
                        inner_level, inner_reason, _ = evaluate_command_safety(
                            inner, mode=mode, _depth=_depth + 1
                        )
                        if inner_level > SafetyLevel.SAFE:
                            _bump(
                                inner_level,
                                f"Inside inline script ({tok}): {inner_reason}",
                            )


    if _depth < 2 and mode == "shell":
        for seg in split_logical_segments(cmd):
            toks = tokenize_segment(seg)
            for i, tok in enumerate(toks[:-1]):
                if tok.lower() in ("-encodedcommand", "-enc", "-e"):
                    b64_payload = _dequote(toks[i + 1])
                    decoded = _decode_powershell_b64(b64_payload)
                    if decoded:
                        inner_level, inner_reason, _ = evaluate_command_safety(
                            decoded, mode=mode, _depth=_depth + 1
                        )
                        _bump(
                            max(inner_level, SafetyLevel.SUSPICIOUS),
                            f"Decoded -EncodedCommand payload: {inner_reason or 'base64-obfuscated command (always at least SUSPICIOUS)'}",
                        )
                    else:
                        _bump(
                            SafetyLevel.SUSPICIOUS,
                            "Unreadable -EncodedCommand payload (possibly malformed or truncated Base64)",
                        )

    if worst_level == SafetyLevel.CRITICAL:
        return worst_level, worst_reason, highlighted

    for seg in split_logical_segments(cmd):
        level, reason = _classify_segment(seg, mode)
        if level > worst_level:
            worst_level, worst_reason = level, reason
            tokens = tokenize_segment(seg)
            if tokens:
                highlighted = highlighted.replace(tokens[0], f"[[{tokens[0]}]]", 1)

    return worst_level, worst_reason, highlighted