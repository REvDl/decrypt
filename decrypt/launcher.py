import re
import subprocess

from .ai import decode_response
from .ui import GREEN, BOLD, DIM, RST, collect_stream

DANGEROUS_PATTERNS = [
    r'rm\s+-rf\s+/?',
    r':\(\)\s*\{\s*:\|\:&\s*\};:',
    r'shutdown', r'reboot', r'init\s+0',
    r'dd\s+if=/dev/zero', r'mkfs',
    r'>\s*/dev/sda', r'curl.*\|.*sh',
    r'wget.*\|.*sh',
]


def get_git_diff():
    try:
        result = subprocess.run(
            ["git", "diff", "--staged"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def execute_command_prompt(
        command: str,
        mode: str,
        client,
        user_text: str,
        target_lang: str,
        auto: bool = False,
        attempt: int = 1,
        max_attempts: int = 3,
):
    clean_command = re.sub(r'^```[a-zA-Z]*\n', '', command)
    clean_command = re.sub(r'\n```$', '', clean_command)
    clean_command = clean_command.strip()

    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, clean_command):
            print(f"\033[31mBlocked dangerous command pattern: {pattern}\033[0m")
            return

    executable = "powershell" if mode == "shell" else "bash"
    flag = "-Command" if mode == "shell" else "-c"

    print(f"\n{GREEN}{BOLD}Generated command (Attempt {attempt}/{max_attempts}):{RST} {clean_command}")
    if not auto:
        confirm = input("Execute command? [Y/n] ").strip().lower()
        if confirm not in ["y", "yes"]:
            print(f"{DIM}Executing canceled.{RST}")
            return

    try:
        result = subprocess.run(
            [executable, flag, clean_command],
            shell=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.stdout and result.stdout.strip():
            print(result.stdout.strip())
        if result.returncode == 0:
            return
        print(f"\n\033[31mError executing command (Code: {result.returncode})\033[0m")
        error_msg = result.stderr.strip() if (result.stderr and result.stderr.strip()) else "Unknown CLI error."
        if error_msg:
            print(f"\033[31m{error_msg}\033[0m")
        if attempt >= max_attempts:
            print(f"\n\033[31m[Self-Healing] Maximum attempts reached. Stopping to prevent loop.{RST}")
            return

        print(f"\n{DIM}[Self-Healing] Sending error report to Gemini...{RST}")
        error_report = (
            f"Original request:\n{user_text}\n\n"
            f"Generated command:\n{clean_command}\n\n"
            f"Error:\n{error_msg}\n\n"
            f"Generate a corrected {'PowerShell' if mode == 'shell' else 'Bash'} command."
        )
        corrected_chunks = decode_response(client, error_report, mode, target_lang)
        corrected_result = collect_stream(corrected_chunks)
        if corrected_result and corrected_result.strip().startswith("\033[31m"):
            print(corrected_result)
            return
        execute_command_prompt(
            command=corrected_result,
            mode=mode,
            client=client,
            user_text=user_text,
            target_lang=target_lang,
            auto=auto,
            attempt=attempt + 1,
            max_attempts=max_attempts,
        )
    except Exception as e:
        print(f"\n\033[31mCommand execution failed system-level: {e}\033[0m")


def process_commit(message: str, auto: bool = False):
    print(f"\n{BOLD}Generated commit:{RST}\n{message}")
    try:
        print(f"\n{DIM}Staged files status:{RST}")
        subprocess.run(["git", "diff", "--stat", "--cached"], check=True)
        print()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    if not auto:
        confirm = input("Run 'git commit -m \"...\"'? [Y/n] ").strip().lower()
        if confirm not in ["y", "yes"]:
            print(f"{DIM}Commit canceled.{RST}")
            return

    print(f"{GREEN}Executing: git commit...{RST}")
    subprocess.run(["git", "commit", "-m", message], check=True)

    if not auto:
        confirm_push = input("Run 'git push'? [Y/n] ").strip().lower()
        if confirm_push not in ["y", "yes"]:
            print(f"{DIM}Push canceled.{RST}")
            return

    print(f"{GREEN}Executing: git push...{RST}")
    subprocess.run(["git", "push"], check=True)