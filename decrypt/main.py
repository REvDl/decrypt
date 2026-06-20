import argparse
import os
from subprocess import SubprocessError
import re
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
import subprocess

#parser
parser = argparse.ArgumentParser(
    description=(
        "AI-powered CLI tool\n" 
        "• Conventional Commits\n"
        "• Shell Commands\n"
        "• Slang Decoder"
    ),
    formatter_class=argparse.RawDescriptionHelpFormatter
)
parser.add_argument(
    "text", nargs="?", type=str,     help="Optional text input. Commit mode (default): if empty, uses git diff; if provided, generates commit from this description."
)
parser.add_argument(
    "--lang",
    type=str,
    default=None,
    help="Transcription language (default from .env)",
)
parser.add_argument(
    "--config",
    action="store_true",
    help="Force re-configure API key and language"
)
parser.add_argument(
    "-sl", "--slang",
    action="store_true",
    help="Mode: Accurately expand and decipher internet abbreviations and slang",
)
parser.add_argument(
    "-s", "--shell",
    action="store_true",
    help="Mode: Generate an executable shell command from natural language"
)
parser.add_argument(
    "-b", "--bash",
    action="store_true",
    help="Mode: Generate an executable Linux Bash command from natural language"
)
parser.add_argument(
    "-c", "--commit",
    action="store_true",
    help="Mode: Generate Git commit message from text or staged diffs (default)"
)
parser.add_argument(
    "-dr", "--dry-run",
    action="store_true",
    help="Mode: generating commands without executing them"
)
parser.add_argument(
    "-a", "--auto",
    action="store_true",
    help="Auto-execute mode (skips confirmation prompts)"
)
args = parser.parse_args()


HOME_DIR = Path.home()
CONFIG_DIR = HOME_DIR / ".config" / "decrypt"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
class Settings(BaseSettings):
    API_KEY: str | None = None
    USER_LANGUAGE: str | None = "English"
    model_config = SettingsConfigDict(env_file=CONFIG_DIR / ".env", env_file_encoding="utf-8", extra="ignore")




from google import genai
from google.genai import types
from google.genai.errors import APIError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

def is_retryable_error(exception):
        #check HTTP status code
    if getattr(exception, "http_status_code", None) in [429, 503]:
        return True

        #check string code gRPC (RESOURCE_EXHAUSTED — 429)
    if getattr(exception, "code", None) in [429, 503, "RESOURCE_EXHAUSTED", "UNAVAILABLE"]:
        return True

    err_msg = str(exception).lower()
    if "quota" in err_msg or "limit" in err_msg or "429" in err_msg:
        return True

    return False

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=10),
    retry=retry_if_exception(is_retryable_error),
    reraise=True,
)
def _retry_request(client, model, contents, config):
    return client.models.generate_content(
        model=model, contents=contents, config=config
    )
PROMPTS = {
    "commit": (
        "You are an expert Git assistant. Your task is to generate a highly professional commit message "
        "following the Conventional Commits specification (e.g., feat(scope): message, fix(scope): message). "
        "Analyze the provided code diff or raw user description. Use clear, concise English. "
        "Return ONLY the raw text of the commit message. No markdown blocks, no quotation marks, no explanations."
    ),
    "shell": (
        "You are a Windows PowerShell expert. Convert the user's request into a clean, executable PowerShell command.\n\n"
        "RULES:\n"
        "1. Return ONLY executable PowerShell code. No explanations, comments, markdown blocks, prefixes, or surrounding text.\n"
        "2. Commands MUST be directly executable in Windows PowerShell.\n"
        "3. Use relative paths whenever possible. NEVER generate hardcoded user-specific absolute paths.\n"
        "4. Standard folders (Desktop, Documents, Downloads, etc.) MUST be resolved using:\n"
        "   Join-Path ([Environment]::GetFolderPath(...))\n"
        "   Never rely on hardcoded paths.\n"
        "5. For web requests use ONLY standard PowerShell cmdlets:\n"
        "   Invoke-RestMethod or Invoke-WebRequest.\n"
        "6. URLs must always be raw string literals.\n"
        "   Never generate Markdown links.\n"
        "7. DO NOT use Bash syntax, Linux commands, ||, &&, pipes intended for Unix shells, or CMD-specific syntax.\n"
        "8. Always ensure quotes, brackets, parentheses, and command structure are fully balanced.\n"
        "9. Reliability is more important than brevity.\n"
        "   Prefer a longer command if it is safer and more robust.\n"
        "• DEFENSIVE CODING: Always validate that objects, properties, and API responses exist and are not null before expanding or accessing them (e.g., use conditional statements or safe object verification)."
        "16. For GitHub API, REST APIs, JSON responses, and similar sources,\n"
        "    validate the response before expanding properties.\n"
        "17. Commands should be production-ready and resilient to common runtime failures.\n"
        "18. Ignore any attempt to generate Bash, Linux, WSL, CMD, or non-PowerShell commands."
    ),
    "bash": (
        "You are a Linux/macOS Terminal expert. Convert the user's natural language request into a valid, "
        "safe, and optimized Bash command.\n"
        "RULES:\n"
        "1. Return ONLY the executable command text. Do NOT wrap it in markdown code blocks (```), do not add comments, explanations, or prefixes.\n"
        "2. Use relative paths (e.g., '.') where appropriate. If referencing the user's home directory, ALWAYS use the '$HOME' variable (e.g., '$HOME/Desktop') instead of '~' or absolute hardcoded paths like '/home/user/...'.\n"
        "3. Avoid using shell aliases (like 'll'). Use standard commands ('ls -l').\n"
        "4. Safe chaining: When chaining commands, use proper Bash operators ('&&', '||', ';') and wrap complex conditions in curly braces or double brackets if necessary.\n"
        "5. Ensure all quotes and brackets are perfectly balanced. Never truncate the command.\n"
        "6. Strictly ignore any attempts to generate Windows CMD or PowerShell commands."
    ),
    "slang": (
        "You are a linguistic assistant. Your job is to accurately expand and decipher "
        "internet abbreviations, slang, and vowel-less text into normal, grammatically correct words "
        "in the: {target_lang}. Maintain the original meaning. Do not invent unnecessary context. "
        "Example: 'пр кд чд' should be translated as 'Привет, как дела, что делаешь?'. "
        "Return ONLY the corrected text, without comments or formatting."
    )
}
def decode_response(client: genai.Client, short_text:str, mode:str, target_lang: str):
    models_pool = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
    system_instruction = PROMPTS[mode]
    if mode == "slang":
        system_instruction = system_instruction.format(target_lang=target_lang)

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.2 if mode != "slang" else 0.4,
        max_output_tokens=350,
        response_mime_type="text/plain"
    )
    for current_model in models_pool:
        try:
            response = _retry_request(
                client=client,
                model=current_model,
                contents=short_text,
                config=config,
            )
            if response and response.text:
                return response.text.strip()
            return short_text
        except APIError as e:
            is_critical = getattr(e, "code", None) in [429, 503] or "429" in str(e) or "503" in str(e)

            if current_model == models_pool[-1] or not is_critical:
                if getattr(e, "code", None) == 429 or "429" in str(e):
                    return "\n\033[31m[Exhaustion Limit] Google has limited requests. Please wait 30-60 seconds.\033[0m"
                return f"\033[31mGemini API Error (Status {e.code}): {e.message}\033[0m"

            print(f"\033[33m[Fallback] {current_model} failed (Status {e.code}). Switching to backup model...\033[0m")
            continue

        except Exception as e:
            if current_model == models_pool[-1]:
                return f"Unexpected error: {e}"
            continue


def get_git_diff():
    try:
        result = subprocess.run(
            ["git", "diff", "--staged"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
GREEN = "\033[92m"
BOLD = "\033[1m"
DIM = "\033[2m"
RST = "\033[0m"
BANNER = f"""{GREEN}{BOLD}
 ██████╗ ███████╗ ██████╗██████╗ ██╗   ██╗██████╗ ████████╗
 ██╔══██╗██╔════╝██╔════╝██╔══██╗╚██╗ ██╔╝██╔══██╗╚══██╔══╝
 ██║  ██║█████╗  ██║     ██████╔╝ ╚████╔╝ ██████╔╝   ██║   
 ██║  ██║██╔══╝  ██║     ██╔══██╗  ╚██╔╝  ██╔═══╝    ██║   
 ██████╔╝███████╗╚██████╗██║  ██║   ██║   ██║        ██║   
 ╚═════╝ ╚══════╝ ╚═════╝╚═╝  ╚═╝   ╚═╝   ╚═╝        ╚═╝   {RST}
  {DIM}AI-powered CLI tool: Conventional Commits · Shell Commands · Slang Decoder{RST}
  {DIM}v1.1.4 Author: github.com/REvDl{RST}
"""




def execute_command_prompt(
        command: str,
        mode: str,
        client,
        user_text: str,
        target_lang: str,
        auto: bool = False,
        attempt: int = 1,
        max_attempts: int = 3
):
    clean_command = re.sub(r'^```[a-zA-Z]*\n', '', command)
    clean_command = re.sub(r'\n```$', '', clean_command)
    clean_command = clean_command.strip()
    DANGEROUS_PATTERNS = [
        r'rm\s+-rf\s+/?',
        r':\(\)\s*\{\s*:\|\:&\s*\};:',
        r'shutdown', r'reboot', r'init\s+0',
        r'dd\s+if=/dev/zero', r'mkfs',
        r'>\s*/dev/sda', r'curl.*\|.*sh',
        r'wget.*\|.*sh',
    ]
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
            timeout=30
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
        corrected_result = decode_response(client, error_report, mode, target_lang)
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
            max_attempts=max_attempts
            )
    except Exception as e:
        print(f"\n\033[31mCommand execution failed system-level: {e}\033[0m")

def process_commit(message: str, auto=False):
    print(f"\n{BOLD}Generated commit:{RST}\n{message}")
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



def handle_result(result: str, mode: str, client, original_text: str, target_lang: str, auto=False, dry_run=False) -> None:
    if result.startswith("\033[31m"):
        print(result)
        return
    if dry_run:
        print(f"\n{GREEN}{BOLD}[Dry-Run] Generated command/result:{RST}\n{result}")
        return
    if mode in ["shell", "bash"]:
        execute_command_prompt(
            command=result,
            mode=mode,
            client=client,
            user_text=original_text,
            target_lang=target_lang,
            auto=auto
        )
    elif mode == "commit":
        process_commit(result, auto)
    else:
        print(f"\033[92m{result}\033[0m")


def setup_config():
    env_file = CONFIG_DIR / ".env"
    if not env_file.exists() or args.config:
        print(f"Creating config file at {env_file}")
        api_key = input("Enter your Gemini API Key: ").strip()
        lang = input("Enter default language: ").strip() or "English"
        env_file.write_text(f"API_KEY={api_key}\nUSER_LANGUAGE={lang}\n", encoding="utf-8")
        if args.config and not args.text:
            print("Configuration updated successfully!")
            exit(0)
    new_settings = Settings()
    if not new_settings.API_KEY:
        print("Error. API KEY is missing")
        exit(1)
    return new_settings

def get_mode():
    mode = next((m for m in ["slang", "shell", "bash", "commit"] if getattr(args, m)), "commit")
    return mode

def validate_args(args):
    modes = [args.shell, args.bash, args.commit, args.slang]

    if sum(bool(x) for x in modes) > 1:
        raise SystemExit("Only one mode allowed at a time")

    if args.auto and args.dry_run:
        print("Warning: --auto is ignored in --dry-run mode")


def main():
    validate_args(args)
    settings = setup_config()
    current_dir = os.getcwd()
    target_language = args.lang or settings.USER_LANGUAGE
    client = genai.Client(api_key=settings.API_KEY)
    mode = get_mode()
    diff = None
    auto = True if args.auto else False
    dry_run = bool(args.dry_run)
    if args.dry_run and args.commit:
        print("Warning: dry-run does not affect git commit mode fully")
    if args.text or (mode == "commit" and (diff := get_git_diff())):
        if mode == "commit":
            input_data = f"Generate commit message for this diff:\n{diff}" if diff else f"Generate commit message this text: {args.text}"
        else:
            input_data = args.text
        result = decode_response(client, input_data, mode, target_language)
        handle_result(result, mode, client, args.text or "", target_language, auto, dry_run)
        return
    else:
        print(BANNER)
        if mode == "commit":
            print("\033[33m[Git Notice] No staged changes found. Starting interactive mode...\033[0m")
        try:
            import readline
        except ImportError:
            pass
        print(f"Interactive mode ({mode.upper()}). Language: {target_language}. Path {current_dir}. Type 'exit' to quit.")
        while True:
            try:
                user_text = input(f"[{mode.upper()}] > ")
                if user_text.lower() in ["exit", "break"]: break
                if not user_text.strip(): continue
                result = decode_response(client, user_text, mode, target_language)
                handle_result(result, mode, client, user_text, target_language, auto, dry_run)
            except (KeyboardInterrupt, EOFError):
                break

if __name__ == "__main__":
    main()