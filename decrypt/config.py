import webbrowser
from getpass import getpass
from pathlib import Path

from google import genai
from google.genai.errors import APIError
from pydantic_settings import BaseSettings, SettingsConfigDict

from . import ui

HOME_DIR = Path.home()
CONFIG_DIR = HOME_DIR / ".config" / "decrypt"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

API_KEY_URL = "https://aistudio.google.com/apikey"
VALIDATION_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]


class Settings(BaseSettings):
    API_KEY: str | None = None
    USER_LANGUAGE: str | None = "English"
    model_config = SettingsConfigDict(
        env_file=CONFIG_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def validate_api_key(api_key: str) -> bool:
    if not api_key:
        return False
    client = genai.Client(api_key=api_key)
    for model in VALIDATION_MODELS:
        try:
            client.models.generate_content(model=model, contents="ping")
            return True
        except APIError:
            continue
        except Exception:
            continue
    return False


def prompt_for_api_key(header: str = "No valid Gemini API key found. Choose an option:") -> str:
    api_key = None
    while True:
        try:
            ui.warning(f"\n{header}")
            ui.dim("  1) Enter API key manually")
            ui.dim("  2) Open Google AI Studio and get one")
            ui.dim("  3) Exit")
            choice = input("Select an option: ").strip()

            if choice == "3":
                raise SystemExit(0)

            if choice == "2":
                webbrowser.open(API_KEY_URL)
                ui.dim("A browser window should open. Create a key, copy it, then paste it below.")
                api_key = getpass("Paste your API key: ").strip()
            elif choice == "1":
                api_key = getpass("Enter your Gemini API Key: ").strip()
            else:
                ui.error("Invalid choice, try again.")
                continue
        except (KeyboardInterrupt, EOFError):
            print()
            ui.warning("Cancelled.")
            raise SystemExit(0)

        if not api_key:
            ui.error("Empty input, try again.")
            continue

        ui.dim("Validating API key...")
        if validate_api_key(api_key):
            ui.success("API key is valid.")
            return api_key

        ui.error("Invalid API key or request failed.")


def write_env(api_key: str, lang: str) -> None:
    env_file = CONFIG_DIR / ".env"
    env_file.write_text(f"API_KEY={api_key}\nUSER_LANGUAGE={lang}\n", encoding="utf-8")


def setup_config(force: bool = False, exit_after_setup: bool = False) -> Settings:
    """
    Loads settings from CONFIG_DIR/.env.
    If the file is missing, the key is invalid, or `force` is True, runs
    interactive setup (with google ai studio choice and validation) first.
    force: re-run configuration even if .env already exists (--config flag).
    exit_after_setup: exit(0) right after saving, without loading Settings
                       (used when user only wants to reconfigure, with no text/mode to run).
    """
    env_file = CONFIG_DIR / ".env"

    if not env_file.exists() or force:
        if env_file.exists():
            ui.dim(f"Reconfiguring {env_file}")
            api_key = prompt_for_api_key("Reconfigure Gemini API key. Choose an option:")
        else:
            ui.dim(f"Creating config file at {env_file}")
            api_key = prompt_for_api_key()
        lang = input("Enter default language: ").strip() or "English"
        write_env(api_key, lang)
        if force and exit_after_setup:
            ui.success("Configuration updated successfully!")
            exit(0)

    settings = Settings()

    if not settings.API_KEY or not validate_api_key(settings.API_KEY):
        api_key = prompt_for_api_key()
        lang = settings.USER_LANGUAGE or "English"
        write_env(api_key, lang)
        settings = Settings()

    return settings