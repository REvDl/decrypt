import argparse
import os

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "AI-powered CLI tool\n"
            "• Conventional Commits\n"
            "• Shell Commands\n"
            "• Slang Decoder"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "text", nargs="?", type=str,
        help="Optional text input. Commit mode (default): if empty, uses git diff; if provided, generates commit from this description."
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
    return parser


def get_mode(args) -> str:
    return next((m for m in ["slang", "shell", "bash", "commit"] if getattr(args, m)), "commit")


def validate_args(args) -> None:
    modes = [args.shell, args.bash, args.commit, args.slang]

    if sum(bool(x) for x in modes) > 1:
        raise SystemExit("Only one mode allowed at a time")

    if args.auto and args.dry_run:
        from . import ui
        ui.warning("Warning: --auto is ignored in --dry-run mode")


def handle_result(result, mode: str, client, original_text: str, target_lang: str, auto=False, dry_run=False) -> None:
    from . import ui
    collected = ui.collect_stream(result)
    if collected.startswith(ui.RED):
        return

    if dry_run:
        print()
        ui.heading("[Dry-Run] Generated command/result:")
        print(collected)
        return

    if mode in ["shell", "bash"]:
        from .launcher import execute_command_prompt
        execute_command_prompt(
            command=collected,
            mode=mode,
            client=client,
            user_text=original_text,
            target_lang=target_lang,
            auto=auto,
        )
    elif mode == "commit":
        from .launcher import process_commit
        process_commit(collected, auto)


def main():
    parser = build_parser()
    args = parser.parse_args()
    from google import genai
    from .ai import decode_response
    from .config import setup_config
    from .launcher import get_git_diff
    from . import ui

    validate_args(args)
    settings = setup_config(force=args.config, exit_after_setup=not args.text)
    current_dir = os.getcwd()
    target_language = args.lang or settings.USER_LANGUAGE

    client = genai.Client(api_key=settings.API_KEY)

    mode = get_mode(args)
    auto = bool(args.auto)
    dry_run = bool(args.dry_run)

    if args.dry_run and args.commit:
        ui.warning("Warning: dry-run does not affect git commit mode fully")

    diff = None
    if args.text or (mode == "commit" and (diff := get_git_diff())):
        if mode == "commit":
            input_data = f"Generate commit message for this diff:\n{diff}" if diff else f"Generate commit message this text: {args.text}"
        else:
            input_data = args.text
        result = decode_response(client, input_data, mode, target_language)
        handle_result(result, mode, client, args.text or "", target_language, auto, dry_run)
        return

    ui.banner()
    if mode == "commit":
        ui.warning("[Git Notice] No staged changes found. Starting interactive mode...")
    try:
        import readline
    except ImportError:
        pass

    ui.dim(f"Interactive mode ({mode.upper()}). Language: {target_language}. Path {current_dir}. Type 'exit' to quit.")
    while True:
        try:
            user_text = input(f"[{mode.upper()}] > ")
            if user_text.lower() in ["exit", "break"]:
                break
            if not user_text.strip():
                continue
            result = decode_response(client, user_text, mode, target_language)
            handle_result(result, mode, client, user_text, target_language, auto, dry_run)
        except (KeyboardInterrupt, EOFError):
            break


if __name__ == "__main__":
    main()