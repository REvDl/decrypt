from decrypt import config
import pytest
from unittest.mock import MagicMock, patch


class TestSetupConfigBasic:
    def test_setup_config_creates_env_file_in_fake_dir(self, fake_config_dir, monkeypatch):
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.delenv("USER_LANGUAGE", raising=False)
        inputs = iter(["1", "Russian"])
        monkeypatch.setattr("builtins.input", lambda *_: next(inputs))
        monkeypatch.setattr(config, "getpass", lambda *_: "my-secret-key")
        monkeypatch.setattr(config, "validate_api_key", lambda key: True)
        settings = config.setup_config(force=False, exit_after_setup=False)
        env_file = fake_config_dir / ".env"
        assert env_file.exists()
        assert settings.API_KEY == "my-secret-key"
        assert settings.USER_LANGUAGE == "Russian"

    def test_setup_config_missing_api_key_exits(self, fake_config_dir, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "3")
        monkeypatch.delenv("API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc_info:
            config.setup_config(force=False, exit_after_setup=False)
        assert exc_info.value.code == 0

    def test_setup_config_force_exits_immediately_without_loading_settings(self, fake_config_dir, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "3")

        with pytest.raises(SystemExit) as exc_info:
            config.setup_config(force=True, exit_after_setup=True)
        assert exc_info.value.code == 0


class TestValidateApiKey:
    def test_empty_key_returns_false(self):
        assert config.validate_api_key("") is False

    def test_first_model_success_returns_true(self):
        with patch.object(config.genai, "Client") as mock_client_cls:
            client = MagicMock()
            client.models.generate_content.side_effect = [None]
            mock_client_cls.return_value = client

            assert config.validate_api_key("some-key") is True
            mock_client_cls.assert_called_once_with(api_key="some-key")
            assert client.models.generate_content.call_count == 1

    def test_falls_back_to_second_model_on_failure(self):
        with patch.object(config.genai, "Client") as mock_client_cls:
            client = MagicMock()
            client.models.generate_content.side_effect = [Exception("down"), None]
            mock_client_cls.return_value = client

            assert config.validate_api_key("some-key") is True
            assert client.models.generate_content.call_count == 2

    def test_all_models_failing_returns_false(self):
        with patch.object(config.genai, "Client") as mock_client_cls:
            client = MagicMock()
            client.models.generate_content.side_effect = Exception("down")
            mock_client_cls.return_value = client

            assert config.validate_api_key("some-key") is False
            assert client.models.generate_content.call_count == len(config.VALIDATION_MODELS)

    def test_api_error_is_caught_same_as_generic_exception(self):
        with patch.object(config.genai, "Client") as mock_client_cls:
            client = MagicMock()
            client.models.generate_content.side_effect = config.APIError(429, {"message": "quota"})
            mock_client_cls.return_value = client

            assert config.validate_api_key("some-key") is False


class TestPromptForApiKey:
    def test_manual_entry_valid_key(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *_: "1")
        monkeypatch.setattr(config, "getpass", lambda *_: "valid-key")
        monkeypatch.setattr(config, "validate_api_key", lambda key: True)

        assert config.prompt_for_api_key() == "valid-key"

    def test_invalid_choice_then_manual_entry(self, monkeypatch):
        inputs = iter(["9", "1"])
        monkeypatch.setattr("builtins.input", lambda *_: next(inputs))
        monkeypatch.setattr(config, "getpass", lambda *_: "valid-key")
        monkeypatch.setattr(config, "validate_api_key", lambda key: True)

        assert config.prompt_for_api_key() == "valid-key"

    def test_exit_choice_raises_systemexit(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *_: "3")

        with pytest.raises(SystemExit) as exc_info:
            config.prompt_for_api_key()
        assert exc_info.value.code == 0

    def test_keyboard_interrupt_raises_systemexit(self, monkeypatch):
        def raise_interrupt(*_):
            raise KeyboardInterrupt

        monkeypatch.setattr("builtins.input", raise_interrupt)

        with pytest.raises(SystemExit) as exc_info:
            config.prompt_for_api_key()
        assert exc_info.value.code == 0

    def test_eof_error_raises_systemexit(self, monkeypatch):
        def raise_eof(*_):
            raise EOFError

        monkeypatch.setattr("builtins.input", raise_eof)

        with pytest.raises(SystemExit) as exc_info:
            config.prompt_for_api_key()
        assert exc_info.value.code == 0

    def test_empty_key_retries(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *_: "1")
        keys = iter(["", "valid-key"])
        monkeypatch.setattr(config, "getpass", lambda *_: next(keys))
        monkeypatch.setattr(config, "validate_api_key", lambda key: True)

        assert config.prompt_for_api_key() == "valid-key"

    def test_invalid_key_retries_until_valid(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *_: "1")
        keys = iter(["bad-key", "good-key"])
        monkeypatch.setattr(config, "getpass", lambda *_: next(keys))
        monkeypatch.setattr(config, "validate_api_key", lambda key: key == "good-key")

        assert config.prompt_for_api_key() == "good-key"

    def test_option_2_opens_browser(self, monkeypatch):
        opened = []
        monkeypatch.setattr(config.webbrowser, "open", lambda url: opened.append(url))
        monkeypatch.setattr("builtins.input", lambda *_: "2")
        monkeypatch.setattr(config, "getpass", lambda *_: "browser-key")
        monkeypatch.setattr(config, "validate_api_key", lambda key: True)

        assert config.prompt_for_api_key() == "browser-key"
        assert opened == [config.API_KEY_URL]

    def test_custom_header_is_shown(self, monkeypatch):
        messages = []
        monkeypatch.setattr(config.ui, "warning", lambda msg: messages.append(msg))
        monkeypatch.setattr("builtins.input", lambda *_: "1")
        monkeypatch.setattr(config, "getpass", lambda *_: "valid-key")
        monkeypatch.setattr(config, "validate_api_key", lambda key: True)

        config.prompt_for_api_key("Reconfigure Gemini API key. Choose an option:")
        assert any("Reconfigure Gemini API key" in msg for msg in messages)


class TestWriteEnv:
    def test_writes_expected_content(self, fake_config_dir):
        config.write_env("my-key", "Russian")

        content = (fake_config_dir / ".env").read_text(encoding="utf-8")
        assert "API_KEY=my-key" in content
        assert "USER_LANGUAGE=Russian" in content


class TestSetupConfig:
    def test_no_env_file_prompts_and_creates(self, monkeypatch, fake_config_dir):
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.setattr(config, "prompt_for_api_key", lambda *a, **kw: "new-key")
        monkeypatch.setattr("builtins.input", lambda *_: "")
        monkeypatch.setattr(config, "validate_api_key", lambda key: True)

        settings = config.setup_config()

        assert settings.API_KEY == "new-key"
        assert (fake_config_dir / ".env").exists()

    def test_force_reprompts_even_with_existing_valid_key(self, monkeypatch, fake_config_dir):
        monkeypatch.delenv("API_KEY", raising=False)
        config.write_env("old-key", "English")

        prompt_mock = MagicMock(return_value="new-key")
        monkeypatch.setattr(config, "prompt_for_api_key", prompt_mock)
        monkeypatch.setattr("builtins.input", lambda *_: "")
        monkeypatch.setattr(config, "validate_api_key", lambda key: True)

        settings = config.setup_config(force=True)

        assert settings.API_KEY == "new-key"
        prompt_mock.assert_called_once()
        assert "Reconfigure" in prompt_mock.call_args[0][0]

    def test_force_and_exit_after_setup_exits(self, monkeypatch, fake_config_dir):
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.setattr(config, "prompt_for_api_key", lambda *a, **kw: "new-key")
        monkeypatch.setattr("builtins.input", lambda *_: "")
        monkeypatch.setattr(config, "validate_api_key", lambda key: True)

        with pytest.raises(SystemExit) as exc_info:
            config.setup_config(force=True, exit_after_setup=True)
        assert exc_info.value.code == 0

    def test_existing_valid_key_does_not_reprompt(self, monkeypatch, fake_config_dir):
        monkeypatch.delenv("API_KEY", raising=False)
        config.write_env("existing-key", "English")

        prompt_mock = MagicMock()
        monkeypatch.setattr(config, "prompt_for_api_key", prompt_mock)
        monkeypatch.setattr(config, "validate_api_key", lambda key: True)

        settings = config.setup_config()

        assert settings.API_KEY == "existing-key"
        prompt_mock.assert_not_called()

    def test_existing_invalid_key_reprompts(self, monkeypatch, fake_config_dir):
        monkeypatch.delenv("API_KEY", raising=False)
        config.write_env("bad-key", "English")

        monkeypatch.setattr(config, "prompt_for_api_key", lambda *a, **kw: "fixed-key")
        monkeypatch.setattr(config, "validate_api_key", lambda key: key == "fixed-key")

        settings = config.setup_config()

        assert settings.API_KEY == "fixed-key"