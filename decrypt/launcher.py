import re
import subprocess

from .ai import decode_response
from . import ui
from .safety import evaluate_command_safety, SafetyLevel


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


def confirm_by_safety_level(level: SafetyLevel, reason: str, highlighted_cmd: str) -> bool:
    """
    Returns True if the command may be executed.
    UX per level:
      SAFE       -> runs immediately or with a plain [Y/n]
      SUSPICIOUS -> bright banner + highlighted token + mandatory 'YES' input
      CRITICAL   -> hard block, no way to bypass
    """
    if level == SafetyLevel.CRITICAL:
        ui.error("=" * 60)
        ui.error("  BLOCKED: a potentially destructive command was detected")
        ui.error(f"  Reason: {reason}")
        ui.error(f"  Command: {highlighted_cmd}")
        ui.error("  Execution is not possible. Edit the command manually")
        ui.error("  if this action is genuinely required.")
        ui.error("=" * 60)
        return False

    if level == SafetyLevel.SUSPICIOUS:
        print()
        ui.warning("⚠ WARNING: this command mutates the system / executes code")
        ui.warning(f"  Reason: {reason}")
        print(f"  Command: {highlighted_cmd}")
        try:
            confirm = input("  Type 'YES' (uppercase) to confirm: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            ui.warning("Cancelled by user.")
            return False
        return confirm == "YES"

    # SAFE
    try:
        confirm = input(f"Run: {highlighted_cmd} ? [Y/n] ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        ui.warning("Cancelled by user.")
        return False
    return confirm in ("", "y", "yes")


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

    safety_mode = "shell" if mode == "shell" else "bash"
    level, reason, highlighted = evaluate_command_safety(clean_command, mode=safety_mode)

    print()
    ui.heading(f"Generated command (Attempt {attempt}/{max_attempts}) [{level.name}]:")
    print(highlighted)

    if level == SafetyLevel.CRITICAL:
        confirm_by_safety_level(level, reason, highlighted)
        return

    # --auto skips confirmation ONLY for SAFE commands.
    # SUSPICIOUS always requires an explicit 'YES', even with --auto,
    # otherwise --auto would become carte blanche for destructive actions.
    if level == SafetyLevel.SUSPICIOUS or not auto or attempt > 1:
        if not confirm_by_safety_level(level, reason, highlighted):
            ui.dim("Executing canceled.")
            return

    executable = "powershell" if mode == "shell" else "bash"
    flag = "-Command" if mode == "shell" else "-c"

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

        # Recursive call re-runs evaluate_command_safety() on the corrected
        # command too — self-healing cannot be used to sneak past the
        # safety tiers, each generated attempt is re-classified from scratch.
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