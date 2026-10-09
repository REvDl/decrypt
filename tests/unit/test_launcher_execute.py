from unittest.mock import patch, MagicMock
import pytest
from decrypt.launcher import execute_command_prompt


def _run(command, mode="bash", auto=False):
    execute_command_prompt(
        command=command,
        mode=mode,
        client=None,
        user_text="test request",
        target_lang="English",
        auto=auto,
    )


class TestExecuteCommandPrompt:
    @patch("decrypt.launcher.subprocess.run")
    def test_execute_success_no_self_healing_triggered(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        execute_command_prompt(
            command="Get-Process",
            mode="shell",
            client=None,
            user_text="show processes",
            target_lang="English",
            auto=True,
        )

        mock_run.assert_called_once()
        called_args = mock_run.call_args[0][0]
        assert called_args[0] == "powershell"
        assert called_args[1] == "-Command"

    @patch("decrypt.launcher.subprocess.run")
    @patch("builtins.input")
    def test_safe_command_plain_enter_confirms(self, mock_input, mock_run):
        mock_input.return_value = ""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        execute_command_prompt(
            command="ls -la",
            mode="bash",
            client=None,
            user_text="list files",
            target_lang="English",
            auto=False,
        )

        mock_run.assert_called_once()

    @patch("decrypt.launcher.subprocess.run")
    @patch("builtins.input")
    def test_safe_command_skips_prompt_with_auto(self, mock_input, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        execute_command_prompt(
            command="git status",
            mode="bash",
            client=None,
            user_text="check status",
            target_lang="English",
            auto=True,
        )

        mock_run.assert_called_once()
        mock_input.assert_not_called()

    @patch("decrypt.launcher.subprocess.run")
    @patch("builtins.input")
    def test_caution_command_prompts_even_with_auto(self, mock_input, mock_run):
        mock_input.return_value = "y"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        _run("mkdir build", auto=True)

        mock_input.assert_called_once()
        mock_run.assert_called_once()

    @patch("decrypt.launcher.subprocess.run")
    @patch("builtins.input")
    def test_caution_command_plain_enter_declines(self, mock_input, mock_run):
        mock_input.return_value = ""   # default is N for CAUTION

        _run("mkdir build", auto=True)

        mock_input.assert_called_once()
        mock_run.assert_not_called()

    @patch("decrypt.launcher.subprocess.run")
    @patch("builtins.input")
    def test_caution_command_without_auto_runs_after_y(self, mock_input, mock_run):
        mock_input.return_value = "y"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        _run("git commit -m x", auto=False)

        mock_run.assert_called_once()

    @patch("decrypt.launcher.subprocess.run")
    @patch("builtins.input")
    def test_caution_command_in_powershell_mode(self, mock_input, mock_run):
        mock_input.return_value = ""

        _run("New-Item a.txt", mode="shell", auto=True)

        mock_input.assert_called_once()
        mock_run.assert_not_called()

    @patch("decrypt.launcher.subprocess.run")
    @patch("builtins.input")
    def test_suspicious_command_runs_after_explicit_yes(self, mock_input, mock_run):
        mock_input.return_value = "YES"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        execute_command_prompt(
            command="rm notes.txt",
            mode="bash",
            client=None,
            user_text="delete the notes file",
            target_lang="English",
            auto=True,
        )

        mock_run.assert_called_once()

    @patch("decrypt.launcher.subprocess.run")
    @patch("builtins.input")
    def test_suspicious_command_declined_never_runs(self, mock_input, mock_run):
        mock_input.return_value = "y"
        execute_command_prompt(
            command="rm notes.txt",
            mode="bash",
            client=None,
            user_text="delete the notes file",
            target_lang="English",
            auto=True,
        )

        mock_run.assert_not_called()

    @patch("decrypt.launcher.subprocess.run")
    @patch("builtins.input")
    def test_suspicious_command_requires_confirmation_even_without_auto(
        self, mock_input, mock_run
    ):
        mock_input.return_value = "YES"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        execute_command_prompt(
            command="git push origin main",
            mode="bash",
            client=None,
            user_text="push my changes",
            target_lang="English",
            auto=False,
        )

        mock_run.assert_called_once()
        mock_input.assert_called_once()

    @patch("decrypt.launcher.subprocess.run")
    @patch("builtins.input")
    def test_unknown_binary_is_not_downgraded_to_caution(self, mock_input, mock_run):
        mock_input.return_value = "y"

        _run("perl -e 1", auto=True)

        mock_run.assert_not_called()

    @patch("decrypt.launcher.subprocess.run")
    @patch("builtins.input")
    def test_command_substitution_cannot_hide_behind_safe_binary(
        self, mock_input, mock_run
    ):
        mock_input.return_value = "y"

        _run("echo $(rm -rf ./x)", auto=True)

        mock_run.assert_not_called()

    @patch("decrypt.launcher.subprocess.run")
    def test_critical_command_never_reaches_subprocess(self, mock_run):
        execute_command_prompt(
            command="rm -rf /",
            mode="bash",
            client=None,
            user_text="delete everything",
            target_lang="English",
            auto=True,
        )
        mock_run.assert_not_called()

    @patch("decrypt.launcher.subprocess.run")
    @patch("builtins.input")
    def test_critical_command_never_prompts_and_never_runs(self, mock_input, mock_run):
        mock_input.return_value = "YES"

        _run("rm -rf /", auto=False)

        mock_input.assert_not_called()
        mock_run.assert_not_called()


class TestSelfHealing:
    """Every corrected command must be re-classified from scratch."""

    @patch("decrypt.launcher.ui.collect_stream", return_value="rm -rf /")
    @patch("decrypt.launcher.decode_response")
    @patch("decrypt.launcher.subprocess.run")
    def test_corrected_critical_command_is_blocked(
        self, mock_run, _mock_decode, _mock_collect
    ):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")

        _run("ls", auto=True)

        # only the original `ls` ran; the "corrected" rm -rf / never did
        mock_run.assert_called_once()

    @patch("builtins.input", return_value="")
    @patch("decrypt.launcher.ui.collect_stream", return_value="ls -la")
    @patch("decrypt.launcher.decode_response")
    @patch("decrypt.launcher.subprocess.run")
    def test_retry_attempt_asks_for_confirmation_even_with_auto(
        self, mock_run, _mock_decode, _mock_collect, mock_input
    ):
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="boom"),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]

        _run("ls", auto=True)

        # attempt 1 skipped the prompt (SAFE + auto), attempt 2 must ask
        mock_input.assert_called_once()
        assert mock_run.call_count == 2

    @patch("builtins.input", return_value="")
    @patch("decrypt.launcher.ui.collect_stream", return_value="ls -la")
    @patch("decrypt.launcher.decode_response")
    @patch("decrypt.launcher.subprocess.run")
    def test_stops_after_max_attempts(
        self, mock_run, _mock_decode, _mock_collect, _mock_input
    ):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")

        _run("ls", auto=True)

        assert mock_run.call_count == 3