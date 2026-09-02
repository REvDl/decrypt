from unittest.mock import patch, MagicMock

from decrypt.launcher import execute_command_prompt


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
    def test_safe_command_skips_prompt_with_auto(self, mock_run):
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