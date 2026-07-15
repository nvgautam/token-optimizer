"""Tests for pre_tool_use_agent hook."""

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from agentflow.hooks.pre_tool_use_agent import main


def _call_main(stdin_data: dict) -> int:
    """Patch sys.stdin and call main(); return exit code."""
    stdin_str = json.dumps(stdin_data)
    with patch("sys.stdin", io.StringIO(stdin_str)):
        with pytest.raises(SystemExit) as exc:
            main()
    return exc.value.code


class TestTaskIdExtraction:
    def test_extracts_task_id_from_addendum_header(self, tmp_path):
        prompt = "Some preamble\n\n## Addendum: T-123\n\nTask details here"
        stdin_data = {"tool_name": "Agent", "tool_input": {"prompt": prompt}}
        pty = tmp_path / "agentflow" / "shell" / "pty_signal.py"
        pty.parent.mkdir(parents=True)
        pty.write_text("")

        with patch("agentflow.hooks.pre_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                code = _call_main(stdin_data)

        assert code == 0
        mock_run.assert_called_once()
        call_cmd = mock_run.call_args[0][0]
        assert "task_start" in call_cmd
        assert "T-123" in call_cmd

    def test_task_start_called_with_correct_task_id(self, tmp_path):
        prompt = "## Addendum: T-456\n\nDo something."
        stdin_data = {"tool_name": "Agent", "tool_input": {"prompt": prompt}}
        pty = tmp_path / "agentflow" / "shell" / "pty_signal.py"
        pty.parent.mkdir(parents=True)
        pty.write_text("")

        with patch("agentflow.hooks.pre_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                code = _call_main(stdin_data)

        assert code == 0
        cmd = mock_run.call_args[0][0]
        assert cmd[-2] == "task_start"
        assert cmd[-1] == "T-456"

    def test_no_task_id_in_prompt_exits_zero(self):
        prompt = "Some prompt with no Addendum header"
        stdin_data = {"tool_name": "Agent", "tool_input": {"prompt": prompt}}

        with patch("subprocess.run") as mock_run:
            code = _call_main(stdin_data)

        assert code == 0
        mock_run.assert_not_called()

    def test_malformed_json_stdin_exits_zero(self):
        with patch("sys.stdin", io.StringIO("NOT JSON {")):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 0

    def test_no_prompt_field_exits_zero(self):
        stdin_data = {"tool_name": "Agent", "tool_input": {}}
        with patch("subprocess.run") as mock_run:
            code = _call_main(stdin_data)
        assert code == 0
        mock_run.assert_not_called()

    def test_addendum_header_at_start_of_line(self, tmp_path):
        """Regex must match at start of line (MULTILINE), not mid-line."""
        prompt = "prefix ## Addendum: T-999\n\n## Addendum: T-777\n\nBody"
        stdin_data = {"tool_name": "Agent", "tool_input": {"prompt": prompt}}
        pty = tmp_path / "agentflow" / "shell" / "pty_signal.py"
        pty.parent.mkdir(parents=True)
        pty.write_text("")

        with patch("agentflow.hooks.pre_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                code = _call_main(stdin_data)

        assert code == 0
        # Should match T-777 (first at line start), not T-999 (mid-line)
        cmd = mock_run.call_args[0][0]
        assert cmd[-1] == "T-777"

    def test_subprocess_exception_does_not_crash_hook(self, tmp_path):
        prompt = "## Addendum: T-321\n\nDetails"
        stdin_data = {"tool_name": "Agent", "tool_input": {"prompt": prompt}}
        pty = tmp_path / "agentflow" / "shell" / "pty_signal.py"
        pty.parent.mkdir(parents=True)
        pty.write_text("")

        with patch("agentflow.hooks.pre_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with patch("subprocess.run", side_effect=OSError("no such file")):
                with pytest.raises(SystemExit) as exc:
                    with patch("sys.stdin", io.StringIO(json.dumps(stdin_data))):
                        main()

        assert exc.value.code == 0
