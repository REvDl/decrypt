"""
safety.py — Four-level safety evaluation system.

Levels:
    SAFE        (0) — Read-only / navigation. Runs immediately or with [Y/n].
    CAUTION     (1) — Minor changes / standard deploys. Requires explicit [y/N].
    SUSPICIOUS  (2) — Mutates state / executes code. Requires mandatory 'YES' input.
    CRITICAL    (3) — Destructive / dangerous. Hard-blocked with no bypass.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class SafetyLevel(IntEnum):
    """Safety thresholds for command execution risks and user confirmation UX."""
    SAFE = 0
    CAUTION = 1
    SUSPICIOUS = 2
    CRITICAL = 3


# POSIX (bash/zsh) — only commands that do NOT mutate system state
POSIX_SAFE = {
    "ls", "dir", "cat", "pwd", "echo", "find", "grep", "egrep", "fgrep",
    "head", "tail", "wc", "sort", "uniq", "less", "more", "file", "stat",
    "whoami", "uname", "date", "env", "printenv", "which", "type", "df",
    "history", "tree", "basename", "dirname", "realpath", "id", "hostname",
}

# Mutates files / executes external code — but legitimate in a dev workflow
POSIX_SUSPICIOUS = {
    "python", "python3", "pip", "pip3", "node", "npm", "npx",
    "docker", "docker-compose", "curl", "wget", "ssh", "scp", "rsync",
    "chmod", "chown", "mv", "tar", "zip", "unzip",
    "kill", "killall", "systemctl", "service", "crontab", "sed", "awk",
    "sudo", "runas",  # privilege escalation -> handled strictly below
    "rm", "eval", "exec", "source",
    "shutdown", "reboot", "poweroff", "halt",
}

# PowerShell — cmdlet names are case-insensitive, so compare in lower()
PS_SAFE = {
    "get-location", "gl", "get-childitem", "gci", "dir", "ls",
    "get-content", "gc", "cat", "type", "get-item", "gi",
    "get-process", "gps", "get-date", "write-host", "write-output",
    "echo", "select-string", "sls", "get-history", "clear-host", "cls",
    "get-command", "gcm", "get-help", "get-module", "get-service",
    "test-path", "resolve-path", "get-acl", "pwd",
    "get-disk", "get-volume", "get-partition", "get-psdrive",
}
PS_SUSPICIOUS = {
    "invoke-restmethod", "irm", "invoke-webrequest", "iwr",
    "start-process", "remove-item", "ri",
    "move-item", "rename-item", "set-content", "sc", "add-content",
    "invoke-expression", "iex", "invoke-command", "icm",
    "set-executionpolicy", "stop-process", "stop-service",
    "start-service", "new-object", "start-job",
    "restart-computer", "stop-computer",
}

POSIX_CAUTION = {"mkdir", "touch", "cp"}

PS_CAUTION = {
    "new-item", "ni", "copy-item", "cpi", "copy", "cp", "mkdir", "md",
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


# "Safe" binaries that become dangerous with certain flags
SAFE_BINARY_DANGEROUS_ARGS = {
    "find": {"-delete", "-exec", "-execdir", "-ok", "-okdir",
             "-fprint", "-fprintf", "-fls"},
    "sort": {"-o", "--output"},
    "tree": {"-o"},
}

_REDIRECT_RE = re.compile(
    r"(?<![<>-])(?:\d*>>?|&>)(?!&)\s*(?!/dev/null\b|\$null\b|nul\b)\S",
    re.IGNORECASE,
)

GIT_READONLY = {"status", "log", "diff", "show", "blame", "shortlog",
                "describe", "rev-parse", "fetch"}
_BRANCH_LIST_FLAGS = {"-a", "--all", "-r", "--remotes", "-v", "-vv", "--list",
                      "-l", "--show-current", "--contains", "--merged", "--no-merged"}


def _classify_git(args: list[str]) -> tuple[SafetyLevel, str]:
    S, C, U = SafetyLevel.SAFE, SafetyLevel.CAUTION, SafetyLevel.SUSPICIOUS
    sub, rest = args[0].lower(), args[1:]

    if sub in GIT_READONLY:
        return S, ""

    if sub == "branch":
        if any(a in {"-D", "-f", "--force", "-M", "-C"} for a in rest):
            return U, "git branch force-delete/overwrite"
        if any(a in {"-d", "--delete", "-m", "--move", "-c", "--copy"} for a in rest) \
                or (rest and rest[0] not in _BRANCH_LIST_FLAGS):
            return C, "git branch creates/changes branches"
        return S, ""

    if sub == "remote":
        if not rest or rest[0] in {"-v", "--verbose", "show", "get-url"}:
            return S, ""
        return C, "git remote changes remote configuration"

    if sub == "config":
        reads = {"--get", "--get-all", "--get-regexp", "--list", "-l"}
        if any(a in reads for a in rest) or (len(rest) == 1 and not rest[0].startswith("-")):
            return S, ""
        return U, "git config can define aliases/hooks that execute code"

    if sub == "stash":
        s = rest[0] if rest else "push"
        if s in {"list", "show"}:
            return S, ""
        if s in {"drop", "clear"}:
            return U, "git stash drop/clear discards saved work"
        return C, "git stash modifies the working tree"

    if sub == "tag":
        if not rest or rest[0] in {"-l", "--list"}:
            return S, ""
        return C, "git tag creates/deletes tags"

    if sub == "commit":
        if "--amend" in rest:
            return U, "git commit --amend rewrites history"
        return C, "git commit creates a commit"

    if sub in {"add", "merge", "cherry-pick", "revert"}:
        return C, f"git {sub} changes the repo"

    if sub == "switch":
        if any(a in {"-f", "--force", "--discard-changes"} for a in rest):
            return U, "git switch may discard uncommitted changes"
        return C, "git switch changes the current branch"

    if sub == "checkout":
        # `git checkout x` may be a branch OR a file restore — can't tell without the FS
        if rest and rest[0] == "-b":
            return C, "git checkout -b creates a branch"
        return U, "git checkout may discard uncommitted changes"

    if sub == "restore":
        if "--staged" in rest and "--worktree" not in rest and "-W" not in rest:
            return C, "git restore --staged only touches the index"
        return U, "git restore discards uncommitted changes"

    if sub == "reset":
        if any(a in {"--hard", "--merge", "--keep"} for a in rest):
            return U, "git reset moves HEAD and may discard changes"
        return C, "git reset changes HEAD/index"

    if sub in {"push", "pull", "rebase", "clean"}:
        return U, f"git {sub} mutates history/remote/working tree"

    return U, f"Unknown git subcommand: {sub}"

def _strip_quoted(s: str) -> str:
    """Removes quotes, only for redirect searches."""
    return re.sub(r"\"[^\"]*\"|'[^']*'", '""', s)


def _extract_substitutions(cmd: str) -> list[str]:
    """Extracts the bodies of $(...), <(...), >(...), and `...` (including nested parentheses)."""
    out: list[str] = []
    i, n = 0, len(cmd)
    while i < n:
        if cmd[i] == "`":
            j = cmd.find("`", i + 1)
            j = n if j == -1 else j
            out.append(cmd[i + 1:j])
            i = j + 1
            continue
        if cmd.startswith(("$(", "<(", ">("), i):
            depth, j = 1, i + 2
            while j < n and depth:
                if cmd[j] == "(":
                    depth += 1
                elif cmd[j] == ")":
                    depth -= 1
                j += 1
            out.append(cmd[i + 2:j - 1 if depth == 0 else j])
            i = j
            continue
        i += 1
    return out


def _dangerous_arg(binname: str, args: list[str]) -> Optional[str]:
    bad = SAFE_BINARY_DANGEROUS_ARGS.get(binname)
    if binname == "env" and args:
        return "env <command> executes arbitrary programs"
    if not bad:
        return None
    for a in args:
        al = a.lower()
        if al in bad or any(al.startswith(b + "=") for b in bad if b.startswith("--")):
            return f"{binname} {a}"
        if binname == "sort" and a.startswith("-") and not a.startswith("--") and "o" in a[1:]:
            return f"{binname} {a}"
    return None


@dataclass(frozen=True)
class SafetyPattern:
    """Regex plus a human-readable description, used for CRITICAL and SUSPICIOUS pattern lists."""
    regex: re.Pattern
    description: str


CRITICAL_PATTERNS: list[SafetyPattern] = [
    SafetyPattern(
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
    SafetyPattern(
        re.compile(
            r"(?:remove-item|ri)\b(?=.*-recurse)(?=.*-force)"
            r".*\b([a-zA-Z]:\\?\s*$|\$env:\w+\s*$)",
            re.IGNORECASE,
        ),
        "Remove-Item -Recurse -Force on a drive root",
    ),
    # rd /s /q C:\   (Windows CMD)
    SafetyPattern(
        re.compile(r"\brd\s+(/s\s+/q|/q\s+/s)\s+[a-zA-Z]:\\?\s*$", re.IGNORECASE),
        "rd /s /q on a drive root",
    ),
    SafetyPattern(
        re.compile(
            r"\b(remove-item|ri|rmdir|rd|rm|del)\b[^;&|]*"
            r"(?:-recurse|-r\b|-rf\b|-fr\b|/s\b)[^;&|]*"
            r"(?:[a-zA-Z]:[\\/]?\*?\s*(?:[;&|]|$)|(?<![\w.])/(?:\*)?\s*(?:[;&|]|$)|\$home\b|~\s*(?:[;&|]|$))",
            re.IGNORECASE,
        ),
        "recursive force-delete targeting a drive root/home/wildcard (flags-then-target)",
    ),
    SafetyPattern(
        re.compile(
            r"\b(remove-item|ri|rmdir|rd|rm|del)\b[^;&|]*"
            r"(?:[a-zA-Z]:[\\/]?\*?\s+|(?<![\w.])/(?:\*)?\s+|\$home\b\s+|~\s+)[^;&|]*"
            r"(?:-recurse|-r\b|-rf\b|-fr\b|/s\b)",
            re.IGNORECASE,
        ),
        "recursive force-delete targeting a drive root/home/wildcard (target-then-flags)",
    ),
    # del /f /s /q C:\*
    SafetyPattern(
        re.compile(r"\bdel\s+(/f\s+/s\s+/q|/s\s+/f\s+/q)\s+[a-zA-Z]:\\", re.IGNORECASE),
        "del /f /s /q on a drive",
    ),
    # dd if=... of=/dev/sdX or /dev/nvme..
    SafetyPattern(
        re.compile(r"\bdd\b.*\bof=/dev/(sd|nvme|hd|disk)\w*", re.IGNORECASE),
        "dd writing directly to a block device",
    ),
    # redirecting output straight to a block device: >/dev/sda
    SafetyPattern(
        re.compile(r">\s*/dev/(sd|nvme|hd|disk)\w*"),
        "output redirected to a block device",
    ),
    # fork bomb :(){ :|:& };:
    SafetyPattern(
        re.compile(r":\s*\(\s*\)\s*\{[^}]*:\s*\|\s*:.*\}\s*;\s*:"),
        "fork bomb",
    ),
    # classic PowerShell download-and-execute cradle:
    # IEX (New-Object Net.WebClient).DownloadString('http://...')
    SafetyPattern(
        re.compile(
            r"(?:iex|invoke-expression)[^;&|]*(?:downloadstring|downloadfile)"
            r"|(?:downloadstring|downloadfile)[^;&|]*(?:iex|invoke-expression)",
            re.IGNORECASE,
        ),
        "download-and-execute cradle (DownloadString/File piped into IEX)",
    ),
    # chmod -R 777 / (opens up permissions on the root filesystem)
    SafetyPattern(
        re.compile(r"\bchmod\s+-R\s+[0-7]{3,4}\s+/\s*(?:[;&|]|$)"),
        "chmod -R on the root filesystem",
    ),
    SafetyPattern(
        re.compile(
            r"\b(?:clear|format|initialize|reset|wipe|remove)-(?:disk|volume|partition)s?\b",
            re.IGNORECASE,
        ),
        "PowerShell disk/volume/partition destructive cmdlet",
    ),
]

SUSPICIOUS_PATTERNS: list[SafetyPattern] = [
    # Invoke-Expression / IEX on downloaded content — classic download cradle
    SafetyPattern(
        re.compile(r"(?:iex|invoke-expression)\s*\(?\s*(?:irm|iwr|invoke-restmethod|invoke-webrequest)", re.IGNORECASE),
        "PowerShell download cradle (IEX on a web request result)",
    ),
    SafetyPattern(
        re.compile(r"curl[^\n|]*\|\s*(?:bash|sh|python3?)\b"),
        "curl | bash — executing an arbitrary remote script",
    ),
    SafetyPattern(
        re.compile(r"while\s*\(\s*\$true\s*\)", re.IGNORECASE),
        "infinite loop (while($true))",
    ),
    SafetyPattern(
        re.compile(r"start-process\s+powershell", re.IGNORECASE),
        "spawns a new PowerShell process",
    ),
    # Downloading remote content is not destructive by itself (no execution
    # implied) — escalated to CRITICAL only when piped into IEX, see above.
    SafetyPattern(
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

        if ch == "&" and (cmd[i - 1:i] in (">", "<") or cmd[i + 1:i + 2] == ">"):
            current.append(ch)
            i += 1
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
    if binname.startswith("mkfs"):
        return SafetyLevel.CRITICAL, f"Destructive utility: {binname}"
    if binname in PRIVILEGE_ESCALATION:
        return SafetyLevel.CRITICAL, f"Privilege escalation attempt: {binname}"

    if binname == "git" and args:
        return _classify_git(args)

    if mode == "shell":
        safe_set, caution_set, suspicious_set = PS_SAFE, PS_CAUTION, PS_SUSPICIOUS
    elif mode == "cmd":
        safe_set, caution_set, suspicious_set = CMD_SAFE, set(), CMD_SUSPICIOUS
    else:
        safe_set, caution_set, suspicious_set = POSIX_SAFE, POSIX_CAUTION, POSIX_SUSPICIOUS

    if binname in safe_set:
        bad = _dangerous_arg(binname, args)
        if bad:
            return SafetyLevel.SUSPICIOUS, f"Flag turns a 'safe' binary into a mutating one: {bad}"
        return SafetyLevel.SAFE, ""
    if binname in caution_set:
        return SafetyLevel.CAUTION, f"Creates or copies files: {binname}"
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
    if _REDIRECT_RE.search(_strip_quoted(cmd)):
        _bump(SafetyLevel.SUSPICIOUS, "Output redirection writes to a file")

    subs = _extract_substitutions(cmd)
    if subs:
        if _depth >= 2:
            _bump(SafetyLevel.SUSPICIOUS, "Nested command substitution (too deep to analyze)")
        else:
            for inner in subs:
                lvl, why, _ = evaluate_command_safety(inner, mode=mode, _depth=_depth + 1)
                if lvl > SafetyLevel.SAFE:
                    _bump(lvl, f"Inside command substitution: {why}")
    for seg in split_logical_segments(cmd):
        level, reason = _classify_segment(seg, mode)
        if level > worst_level:
            worst_level, worst_reason = level, reason
            tokens = tokenize_segment(seg)
            if tokens:
                highlighted = highlighted.replace(tokens[0], f"[[{tokens[0]}]]", 1)

    return worst_level, worst_reason, highlighted