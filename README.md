```
 ██████╗ ███████╗ ██████╗██████╗ ██╗   ██╗██████╗ ████████╗
 ██╔══██╗██╔════╝██╔════╝██╔══██╗╚██╗ ██╔╝██╔══██╗╚══██╔══╝
 ██║  ██║█████╗  ██║     ██████╔╝ ╚████╔╝ ██████╔╝   ██║   
 ██║  ██║██╔══╝  ██║     ██╔══██╗  ╚██╔╝  ██╔═══╝    ██║   
 ██████╔╝███████╗╚██████╗██║  ██║   ██║   ██║        ██║   
 ╚═════╝ ╚══════╝ ╚═════╝╚═╝  ╚═╝   ╚═╝   ╚═╝        ╚═╝   
```
AI-powered CLI tool that connects natural language with developer workflows:

- Git commit generation (with optional auto-commit and auto-push)
- Shell command generation (PowerShell & Linux Bash support)
- Slang / abbreviation decoding
- Streaming output — responses print in real time as they generate
- Four-tier command safety system, self-healing shell commands, and a dry-run mode

Powered by Google Gemini API.

---

## Why

Writing a commit message, or figuring out the right shell command, usually means breaking flow: open a browser tab or a separate AI chat, copy-paste context back and forth, then come back to the terminal to actually run something. `decrypt` skips that round-trip — it works right where you already are.

For commits specifically: it shows a `git diff --stat --cached` preview so you can see exactly what's changing, then commits and pushes in one go if it looks right. No extra window, no copy-pasting a diff into a chat.

(The slang decoder is the odd one out — it's the original joke feature this tool started as. Kept it around as a nod to where `decrypt` came from.)

---

## Features

### 1. Commit Generator (default mode)
Generates Conventional Commit messages from:
- staged git diff (`git diff --staged`)
- or manual input text

Shows a `git diff --stat --cached` preview before asking for confirmation, then prompts to run `git commit` and `git push`.

```bash
# From staged diff
git add .
decrypt

# From description
decrypt "fix auth bug in jwt middleware"

# Auto-execute (skips the commit and push prompts)
decrypt --auto
```

In this mode the model only writes the commit *message*. The `git commit` and `git push` commands are fixed in code and run without a shell, so the safety classifier below does not apply here. `--auto` skips both confirmations.

---

> [!WARNING]
> `decrypt` generates and executes shell commands via an LLM. The safety
> system below is a **heuristic classifier, not a sandbox**. It reduces the
> chance of a bad command running, but it cannot guarantee it. Always read
> the command before confirming.

### 2. Shell Command Generator
Convert natural language into executable terminal commands. Supports both PowerShell and Bash.

```bash
# Windows PowerShell (default shell mode)
decrypt -s "find all png files larger than 10MB and delete them"

# Linux / macOS Bash
decrypt -b "kill all processes on port 3000"
```

Every generated command is classified before it can run. Example of what a risky one looks like:

```
Generated command (Attempt 1/3) [SUSPICIOUS]:
Get-ChildItem -Recurse -Force | [[Remove-Item]] -Recurse -Force

⚠ WARNING: this command mutates the system / executes code
  Reason: Command mutates state / executes code: remove-item
  Command: Get-ChildItem -Recurse -Force | [[Remove-Item]] -Recurse -Force
  Type 'YES' (uppercase) to confirm:
```

#### Safety levels

| Level | Meaning | Confirmation | With `--auto` |
|---|---|---|---|
| `SAFE` | Read-only / navigation (`ls`, `git status`, `Get-ChildItem`) | `[Y/n]`, Enter confirms | Runs without asking |
| `CAUTION` | Local, easily reversible changes (`mkdir`, `touch`, `cp`, `git add`, `git commit`) | `[y/N]`, Enter declines | Still asks |
| `SUSPICIOUS` | Mutates state or executes code (`rm`, `curl`, `npm`, `git push`), or anything unrecognized | Type `YES` in uppercase | Still asks |
| `CRITICAL` | Potentially destructive (`rm -rf /`, `dd` to a disk, fork bombs, `Format-Volume`) | Hard block, no bypass | Blocked |

`--auto` only skips the prompt for `SAFE` commands. It never lowers the bar for the other levels.

#### What the classifier looks at

- **Command and subcommand**, per shell. Unknown binaries are `SUSPICIOUS`, not allowed by default. In PowerShell mode, aliases like `rm`, `curl` and `python` are not in the cmdlet lists, so they also land in `SUSPICIOUS`.
- **Flags that change meaning.** `git branch` lists branches, `git branch -D` deletes one. `find` is read-only, `find -delete` and `find -exec` are not. The same applies to `sort -o`, `env <command>`, `git reset --hard`, `git commit --amend`, `git stash drop` and others.
- **Command substitution** (`$(...)`, backticks, `<(...)`) is analyzed recursively, so `echo $(rm -rf x)` is judged by what is inside.
- **Output redirection** (`>`, `>>`, `2>`) counts as a write. `2>&1` and redirects to `/dev/null` do not.
- **Inline scripts** (`python -c`, `powershell -Command`) and PowerShell `-EncodedCommand` payloads are decoded and re-evaluated. An unreadable payload is `SUSPICIOUS`.
- **Privilege escalation** (`sudo`, `runas`, `su`) is `CRITICAL`: once everything is allowed as root, the rest of the checks mean nothing.
- **Download-and-execute** patterns: `curl ... | bash` is `SUSPICIOUS`, `IEX (...DownloadString(...))` is `CRITICAL`.

A chain such as `mkdir x && rm y` is judged by its worst part.

#### Self-healing and other guards

- **Self-healing.** If a command fails, the error is sent back to the model and a corrected command is generated, up to 3 attempts.
- **Corrections are re-classified from scratch.** A "fixed" command goes through the same checks as the original, and retries always ask for confirmation, even with `--auto`.
- **30s timeout.** Commands can't hang indefinitely.

#### Known limits

- Detection is pattern-based. A script file run via `python script.py` is classified as `SUSPICIOUS`, but its contents are not inspected.
- `CRITICAL` patterns match the whole command string, including text inside quotes, so a quoted `rm -rf /` in an `echo` is still blocked. This is intentional: a false block is cheaper than a missed one.
- `git checkout <name>` is `SUSPICIOUS` because it can't be told apart from a file restore without looking at the filesystem. `git switch` is `CAUTION`.

---

### 3. Slang Decoder
Expands internet slang, abbreviations, and vowel-less text into readable text.

```bash
decrypt -sl "hru btw idk"
```

---

### 4. Interactive Mode
Run without input arguments to start a loop:

```bash
decrypt
```

---

### 5. Dry-Run Mode (`--dry-run`)
Only generates output, never executes anything.

```bash
decrypt --dry-run -s "delete all node_modules folders"
decrypt --dry-run -cm "add caching layer for api"
```

---

## Installation

### From PyPI
```bash
pip install decrypt
```

### Using pipx
```bash
pipx install decrypt
```

### Local development install
```bash
git clone https://github.com/REvDl/decrypt.git
cd decrypt
pip install .
```

---

## Configuration

On first run, the tool configures automatically:
- Gemini API key
- Default language

Stored at:
```
~/.config/decrypt/.env
```

Reset configuration:
```bash
decrypt --config
```

---

## CLI Usage

```
usage: decrypt [-h] [-cm] [-s] [-b] [-sl] [-c] [-l LANG] [-dr] [-a] [text]

AI-powered CLI tool
• Conventional Commits
• Shell Commands
• Slang Decoder

positional arguments:
  text                  Optional text input. Commit mode (default): if empty, uses git diff; if provided, generates commit from this description.

options:
  -h, --help            show this help message and exit
  -cm, --commit         Mode: Generate Git commit message from text or staged diffs (default)
  -s, --shell           Mode: Generate an executable shell command from natural language
  -b, --bash            Mode: Generate an executable Linux Bash command from natural language
  -sl, --slang          Mode: Accurately expand and decipher internet abbreviations and slang

  -c, --config          Force re-configure API key and language
  -l, --lang LANG       Transcription language (default from .env)
  -dr, --dry-run        Mode: generating commands without executing them
  -a, --auto            Auto-execute mode (skips confirmation for SAFE commands and commit/push)
```

---

## Development

Tests use `pytest`:

```bash
pip install pytest
pytest -q
```

- `tests/unit/test_launcher_safety.py` — classification of commands into the four levels, parser robustness, and the confirmation prompts (defaults, case sensitivity, cancel behavior).
- `tests/unit/test_launcher_execute.py` — `execute_command_prompt`: what reaches `subprocess`, how `--auto` interacts with each level, and self-healing re-classification.

When a command is found to be misclassified, add it as a row in the parametrized tests first, then fix the classifier.

---

## Tech Stack

- Python 3.10+
- Google Gemini API (`google-genai`)
- Tenacity (with model fallback handling)
- Pydantic Settings
- argparse
- pytest (development)

## Project structure

```
decrypt/
├── decrypt/
│   ├── __init__.py
│   ├── __main__.py       # python -m decrypt
│   ├── ai.py             # Gemini API calls, streaming, model fallback
│   ├── cli.py            # argparse, entry point
│   ├── config.py         # read/write .env config, first-run setup
│   ├── launcher.py       # command execution, confirmation UX, self-healing
│   ├── safety.py         # four-tier command classifier (SAFE/CAUTION/SUSPICIOUS/CRITICAL)
│   └── ui.py             # shared terminal styling (colors, banner)
├── tests/
│   └── unit/
        ├── test_ai.py
        ├── test_cli_args.py
        ├── test_config.py
        ├── test_launcher_execute.py
│       └── test_launcher_safety.py
├── pyproject.toml
├── LICENSE
├── requirements.txt
├── .env.example
└── README.md
```