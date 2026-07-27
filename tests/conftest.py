import pytest


@pytest.fixture()
def fake_config_dir(tmp_path, monkeypatch):
    from decrypt import config

    fake_dir = tmp_path / ".config" / "decrypt"
    fake_dir.mkdir(parents=True)

    monkeypatch.setattr(config, "CONFIG_DIR", fake_dir)
    monkeypatch.setitem(config.Settings.model_config, "env_file", fake_dir / ".env")

    return fake_dir


@pytest.fixture()
def fake_api_key(monkeypatch):
    monkeypatch.setenv("API_KEY", "test_fake_key")
    monkeypatch.setenv("USER_LANGUAGE", "English")


@pytest.fixture(autouse=True)
def isolated_env(fake_config_dir, fake_api_key):
    pass