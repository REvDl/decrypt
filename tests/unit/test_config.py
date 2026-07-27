from decrypt import config
import pytest

def test_setup_config_creates_env_file_in_fake_dir(fake_config_dir, monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("USER_LANGUAGE", raising=False)
    answers = iter(["my-secret-key", "Russian"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    settings = config.setup_config(force=False, exit_after_setup=False)

    env_file = fake_config_dir / ".env"
    assert env_file.exists()
    assert settings.API_KEY == "my-secret-key"
    assert settings.USER_LANGUAGE == "Russian"


def test_setup_config_missing_api_key_exits(fake_config_dir, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    monkeypatch.delenv("API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        config.setup_config(force=False, exit_after_setup=False)
    assert exc_info.value.code == 1


def test_setup_config_force_exits_immediately_without_loading_settings(fake_config_dir, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "some-value")

    with pytest.raises(SystemExit) as exc_info:
        config.setup_config(force=True, exit_after_setup=True)
    assert exc_info.value.code == 0