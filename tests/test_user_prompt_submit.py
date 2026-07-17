"""Tests for user_prompt_submit hook — task lifecycle and pty_signal integration."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentflow.hooks.ups_task_sync import _cleanup_merged_in_flight


def _setup_workspace(tmp_path: Path, task_id: str = "T-50", sid: str = "test-sid") -> tuple[Path, Path]:
    """Create minimal workspace: agentflow_dir, tasks_in_flight, tasks.json, pty_signal stub."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    # SID-scoped tasks_in_flight
    sessions_dir = agentflow_dir / "sessions" / sid
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "tasks_in_flight.json").write_text(json.dumps([task_id]))

    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps({"tasks": [{"task_id": task_id, "status": "pending"}]}))

    pty = tmp_path / "agentflow" / "shell" / "pty_signal.py"
    pty.parent.mkdir(parents=True)
    pty.write_text("#!/usr/bin/env python3\nimport sys; sys.exit(0)\n")

    cleanup = tmp_path / "agentflow" / "tools" / "cleanup_tasks.py"
    cleanup.parent.mkdir(parents=True, exist_ok=True)
    cleanup.write_text("#!/usr/bin/env python3\nimport sys; sys.exit(0)\n")

    return agentflow_dir, tasks_file


class TestCleanupMergedInFlight:
    def test_cleanup_merged_calls_task_done_signal(self, tmp_path):
        """After marking a merged task complete, pty_signal.py task_done must be called."""
        agentflow_dir, tasks_file = _setup_workspace(tmp_path, "T-50", "test-sid")

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch(
            "agentflow.hooks.ups_task_sync._fetch_merged_pr_titles",
            return_value={"feat(T-50): something"},
        ):
            with patch("agentflow.hooks.ups_task_sync.TaskDB") as mock_db_class:
                mock_db = MagicMock()
                mock_db.mark_complete.return_value = "marked"
                mock_db_class.return_value = mock_db
                with patch("agentflow.hooks.ups_task_sync.subprocess.run", return_value=mock_result) as mock_run:
                    _cleanup_merged_in_flight(agentflow_dir, sid="test-sid")

        task_done_calls = [c for c in mock_run.call_args_list if "task_done" in str(c)]
        assert len(task_done_calls) >= 1
        assert "T-50" in str(task_done_calls[0])

    def test_cleanup_task_done_not_called_when_not_merged(self, tmp_path):
        agentflow_dir, tasks_file = _setup_workspace(tmp_path, "T-51", "s2")

        with patch(
            "agentflow.hooks.ups_task_sync._fetch_merged_pr_titles",
            return_value=set(),
        ):
            with patch("agentflow.hooks.ups_task_sync.subprocess.run") as mock_run:
                _cleanup_merged_in_flight(agentflow_dir, sid="s2")

        task_done_calls = [c for c in mock_run.call_args_list if "task_done" in str(c)]
        assert len(task_done_calls) == 0

    def test_cleanup_no_in_flight_file_is_noop(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        with patch("agentflow.hooks.ups_task_sync.subprocess.run") as mock_run:
            _cleanup_merged_in_flight(agentflow_dir, sid="nosid")
        mock_run.assert_not_called()

    def test_cleanup_merged_marks_task_complete_in_tasks_json(self, tmp_path):
        agentflow_dir, tasks_file = _setup_workspace(tmp_path, "T-52", "s3")

        mock_result = MagicMock()
        mock_result.returncode = 0

        def mock_mark_complete(task_id):
            # Update tasks.json to simulate TaskDB behavior
            data = json.loads(tasks_file.read_text())
            for task in data.get("tasks", []):
                if task["task_id"] == task_id:
                    task["status"] = "complete"
            tasks_file.write_text(json.dumps(data, indent=2))
            return "marked"

        with patch(
            "agentflow.hooks.ups_task_sync._fetch_merged_pr_titles",
            return_value={"feat(T-52): new feature"},
        ):
            with patch("agentflow.hooks.ups_task_sync.TaskDB") as mock_db_class:
                mock_db = MagicMock()
                mock_db.mark_complete.side_effect = mock_mark_complete
                mock_db_class.return_value = mock_db
                with patch("agentflow.hooks.ups_task_sync.subprocess.run", return_value=mock_result):
                    _cleanup_merged_in_flight(agentflow_dir, sid="s3")

        data = json.loads(tasks_file.read_text())
        assert data["tasks"][0]["status"] == "complete"

    def test_cleanup_task_done_subprocess_exception_does_not_crash(self, tmp_path):
        agentflow_dir, tasks_file = _setup_workspace(tmp_path, "T-53", "s4")

        call_count = 0

        def side_effect(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if "task_done" in cmd:
                raise OSError("signal script missing")
            r = MagicMock()
            r.returncode = 0
            return r

        with patch(
            "agentflow.hooks.ups_task_sync._fetch_merged_pr_titles",
            return_value={"fix(T-53): bug"},
        ):
            with patch("agentflow.hooks.ups_task_sync.TaskDB") as mock_db_class:
                mock_db = MagicMock()
                mock_db.mark_complete.return_value = "marked"
                mock_db_class.return_value = mock_db
                with patch("agentflow.hooks.ups_task_sync.subprocess.run", side_effect=side_effect):
                    # Should not raise
                    _cleanup_merged_in_flight(agentflow_dir, sid="s4")

    def test_cleanup_task_done_called_with_sys_executable(self, tmp_path):
        """Verify pty_signal.py is called with sys.executable (no shell=True)."""
        agentflow_dir, tasks_file = _setup_workspace(tmp_path, "T-54", "s5")

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch(
            "agentflow.hooks.ups_task_sync._fetch_merged_pr_titles",
            return_value={"chore(T-54): something"},
        ):
            with patch("agentflow.hooks.ups_task_sync.TaskDB") as mock_db_class:
                mock_db = MagicMock()
                mock_db.mark_complete.return_value = "marked"
                mock_db_class.return_value = mock_db
                with patch("agentflow.hooks.ups_task_sync.subprocess.run", return_value=mock_result) as mock_run:
                    _cleanup_merged_in_flight(agentflow_dir, sid="s5")

        task_done_calls = [c for c in mock_run.call_args_list if "task_done" in str(c)]
        assert len(task_done_calls) >= 1
        cmd = task_done_calls[0][0][0]
        # First element must be sys.executable, not a shell string
        assert cmd[0] == sys.executable
        assert "shell" not in task_done_calls[0][1] or task_done_calls[0][1].get("shell") is not True
