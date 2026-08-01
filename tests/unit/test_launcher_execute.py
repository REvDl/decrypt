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
    def test_blocked_command_never_reaches_subprocess(self, mock_run):
        execute_command_prompt(
            command="rm -rf /",
            mode="bash",
            client=None,
            user_text="delete everything",
            target_lang="English",
            auto=True,
        )
        mock_run.assert_not_called()