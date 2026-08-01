import pytest
from unittest.mock import patch
from decrypt.cli import build_parser, get_mode, validate_args, handle_result


class TestCliParsingAndValidation:
    def test_default_mode_is_commit(self):
        parser = build_parser()
        args = parser.parse_args(["some text"])
        assert get_mode(args) == "commit"

    def test_shell_flag_sets_mode(self):
        parser = build_parser()
        args = parser.parse_args(["-s", "list files"])
        assert get_mode(args) == "shell"

    def test_multiple_modes_raises(self):
        parser = build_parser()
        args = parser.parse_args(["-s", "-b", "text"])
        with pytest.raises(SystemExit) as exc_info:
            validate_args(args)
        assert exc_info.value.code == "Only one mode allowed at a time"
        assert "Only one mode" in str(exc_info.value)

    def test_auto_and_dry_run_warns_but_does_not_raise(self, monkeypatch, capsys):
        parser = build_parser()
        args = parser.parse_args(["--auto", "--dry-run", "-s", "text"])
        validate_args(args)
        captured = capsys.readouterr()
        assert "ignored" in captured.out.lower()

    @pytest.mark.parametrize("args,expected", [
        (["-cm", "text"], "commit"),
        (["-sl", "text"], "slang"),
        (["-b", "text"], "bash"),
    ])
    def test_get_mode_various_flags(self, args, expected):
        parser = build_parser()
        parsed = parser.parse_args(args)
        assert get_mode(parsed) == expected


class TestHandleResult:
    @patch("decrypt.launcher.process_commit")
    @patch("decrypt.launcher.execute_command_prompt")
    def test_slang_mode_does_not_call_launcher_functions(self, mock_execute, mock_commit):
        handle_result(
            result=iter(["привет как дела"]),
            mode="slang",
            client=None,
            original_text="прв кк дл",
            target_lang="English",
        )
        mock_execute.assert_not_called()
        mock_commit.assert_not_called()

    @patch("decrypt.launcher.process_commit")
    @patch("decrypt.launcher.execute_command_prompt")
    def test_commit_mode_calls_process_commit(self, mock_execute, mock_commit):
        handle_result(
            result=iter(["feat: add auth"]),
            mode="commit",
            client=None,
            original_text="add auth",
            target_lang="English",
            auto=True,
        )
        mock_commit.assert_called_once()
        mock_execute.assert_not_called()