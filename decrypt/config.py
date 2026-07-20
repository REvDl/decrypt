from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

HOME_DIR = Path.home()
CONFIG_DIR = HOME_DIR / ".config" / "decrypt"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    API_KEY: str | None = None
    USER_LANGUAGE: str | None = "English"
    model_config = SettingsConfigDict(
        env_file=CONFIG_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def setup_config(force: bool = False, exit_after_setup: bool = False) -> Settings:
    """
    Loads settings from CONFIG_DIR/.env.
    If the file is missing or `force` is True, runs interactive setup first.

    force: re-run configuration even if .env already exists (--config flag).
    exit_after_setup: exit(0) right after saving, without loading Settings
                       (used when user only wants to reconfigure, with no text/mode to run).
    """
    env_file = CONFIG_DIR / ".env"
    if not env_file.exists() or force:
        print(f"Creating config file at {env_file}")
        api_key = input("Enter your Gemini API Key: ").strip()
        lang = input("Enter default language: ").strip() or "English"
        env_file.write_text(f"API_KEY={api_key}\nUSER_LANGUAGE={lang}\n", encoding="utf-8")
        if force and exit_after_setup:
            print("Configuration updated successfully!")
            exit(0)

    settings = Settings()
    if not settings.API_KEY:
        print("Error. API KEY is missing")
        exit(1)
    return settings