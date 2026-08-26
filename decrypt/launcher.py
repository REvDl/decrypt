import re
import subprocess

from .ai import decode_response
from . import ui
import shlex
import os

ALLOWED_BINARIES = {
    # base
    "ls", "dir", "cat", "type", "grep", "findstr", "find", "echo", "pwd", "cd",
    "mkdir", "cp", "copy", "mv", "move", "touch", "head", "tail", "wc", "sort",
    # dev
    "git", "npm", "npx", "pip", "python", "python3", "node", "docker",
}


BLOCKED_KEYWORDS = {
    "sudo", "runas", "rm", "del", "rd", "rmdir", "format", "shutdown",
    "reboot", "diskpart", "mkfs", "dd",
}


def is_command_safe(cmd: str) -> tuple[bool, str]:
    parts = re.split(r'[;&|]+', cmd)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        try:
            tokens = shlex.split(part, posix=False)
        except ValueError:
            return False, "Failed to parse the command"
        if not tokens:
            continue
        binname = os.path.basename(tokens[0]).lower().replace(".exe", "")
        if binname in BLOCKED_KEYWORDS:
            return False, f"Prohibited command: {binname}"
        if binname not in ALLOWED_BINARIES:
            return False, f"Command outside allowlist: {binname}"
    return True, ""

def get_git_diff() -> str:
    try:
        result = subprocess.run(
            ["git", "diff", "--staged"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, UnicodeDecodeError):
        return ""


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


    is_safe, reason = is_command_safe(clean_command)
    if not is_safe:
        ui.error(f"Blocked: {reason}")
        return


    executable = "powershell" if mode == "shell" else "bash"
    flag = "-Command" if mode == "shell" else "-c"

    print()
    ui.heading(f"Generated command (Attempt {attempt}/{max_attempts}):")
    print(clean_command)

    if not auto or attempt > 1:
        try:
            confirm = input("Execute command? [Y/n] ").strip().lower()
        except KeyboardInterrupt:
            ui.warning("Operation cancelled.")
            return
        if confirm not in ["y", "yes"]:
            ui.dim("Executing canceled.")
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

        ui.error(f"\nError executing command (Code: {result.returncode})")
        error_msg = result.stderr.strip() if (result.stderr and result.stderr.strip()) else "Unknown CLI error."
        if error_msg:
            ui.error(error_msg)

        if attempt >= max_attempts:
            ui.error(f"\n[Self-Healing] Maximum attempts reached. Stopping to prevent loop.")
            return

        ui.dim(f"\n[Self-Healing] Sending error report to Gemini...")
        error_report = (
            f"Original request:\n{user_text}\n\n"
            f"Generated command:\n{clean_command}\n\n"
            f"Error:\n{error_msg}\n\n"
            f"Generate a corrected {'PowerShell' if mode == 'shell' else 'Bash'} command."
        )
        corrected_chunks = decode_response(client, error_report, mode, target_lang)
        corrected_result = ui.collect_stream(corrected_chunks)
        if corrected_result and corrected_result.strip().startswith(ui.RED):
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
        ui.error(f"\nCommand execution failed system-level: {e}")


def process_commit(message: str, auto: bool = False):
    print()
    print(f"{ui.BOLD}Generated commit:{ui.RST}\n{message}")
    try:
        ui.dim("\nStaged files status:")
        subprocess.run(["git", "diff", "--stat", "--cached"], check=True)
        print()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    if not auto:
        try:
            confirm = input("Run 'git commit -m \"...\"'? [Y/n] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            ui.warning("Commit cancelled by user.")
            return

        if confirm not in ["y", "yes"]:
            ui.dim("Commit canceled.")
            return

    ui.success("Executing: git commit...")
    try:
        subprocess.run(["git", "commit", "-m", message], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        ui.error(f"Failed to execute git commit: {e}")
        return

    if not auto:
        try:
            confirm_push = input("Run 'git push'? [Y/n] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            ui.warning("Push cancelled by user.")
            return

        if confirm_push not in ["y", "yes"]:
            ui.dim("Push canceled.")
            return

    ui.success("Executing: git push...")
    try:
        subprocess.run(["git", "push"], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        ui.error(f"Failed to execute git push: {e}")

    ui.success("Executing: git push...")
    subprocess.run(["git", "push"], check=True)