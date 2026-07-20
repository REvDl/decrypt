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
- Self-healing shell commands, dangerous-command blocking, and a dry-run mode for safety

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

# Auto-execute (skip prompts)
decrypt --auto
```

---

### 2. Shell Command Generator
Convert natural language into executable terminal commands. Supports both PowerShell and Bash.

```bash
# Windows PowerShell (default shell mode)
decrypt -s "find all png files larger than 10MB and delete them"

# Linux / macOS Bash
decrypt -b "kill all processes on port 3000"
```

Built-in safety guards:
- **Self-healing** — a failed command is automatically re-generated and corrected by the AI
- **Dangerous command blocking** — protection against `rm -rf`, fork bombs, and similar
- **30s timeout** — commands can't hang indefinitely

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
decrypt --dry-run -c "add caching layer for api"
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
git clone https://github.com/REvDl/Scripts.git
cd Scripts/automation_tool/DecrypMessage
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
  -a, --auto            Auto-execute mode (skips confirmation prompts)
```

---

## Tech Stack

- Python 3.10+
- Google Gemini API (`google-genai`)
- Tenacity (with model fallback handling)
- Pydantic Settings
- argparse

## Project structure

```
decrypt/
├── decrypt/
│   ├── __init__.py
│   ├── __main__.py       # python -m decrypt
│   ├── ai.py               # Gemini API calls, streaming, model fallback
│   ├── cli.py             # argparse, entry point
│   ├── config.py          # read/write .env config, first-run setup
│   ├── launcher.py        # command execution, self-healing, safety checks
│   └── ui.py               # shared terminal styling (colors, banner)
├── pyproject.toml
├── LICENSE
├── requirements.txt
├── .env.example
└── README.md
```