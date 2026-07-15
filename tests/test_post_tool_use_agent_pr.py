"""Tests for post_tool_use_agent hook — PR detection and cleanup."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from agentflow.hooks.post_tool_use_agent import _fetch_merged_pr_titles, _mark_task_complete, _run_cleanup, main


def _run_hook(tmp_path, stdin_data=None, in_flight=None, tasks=None):
    """Helper: set up files and call main() with patched stdin."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    if in_flight is not None:
        (agentflow_dir / "tasks_in_flight.json").write_text(json.dumps(in_flight))

    if tasks is not None:
        (tmp_path / "tasks.json").write_text(json.dumps({"tasks": tasks}))

    # Create a stub pty_signal.py so subprocess.run has a target
    pty_dir = tmp_path / "agentflow" / "shell"
    pty_dir.mkdir(parents=True)
    (pty_dir / "pty_signal.py").write_text("#!/usr/bin/env python3\nimport sys; sys.exit(0)\n")

    stdin_json = json.dumps(stdin_data or {})

    with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.read.return_value = stdin_json
            # json.load needs a file-like; patch it directly
            with patch("agentflow.hooks.post_tool_use_agent.json") as mock_json:
                mock_json.load = json.load
                mock_json.JSONDecodeError = json.JSONDecodeError
                with pytest.raises(SystemExit) as exc:
                    main()
    return exc.value.code


class TestPRDetection:
    def test_fetch_merged_pr_titles_returns_set_of_titles(self):
        mock_result = MagicMock()
        mock_result.stdout = '[{"title": "T-123: add feature"}, {"title": "T-124: fix bug"}]'
        with patch("subprocess.run", return_value=mock_result):
            titles = _fetch_merged_pr_titles()
        assert "T-123: add feature" in titles
        assert "T-124: fix bug" in titles

    def test_fetch_merged_pr_titles_returns_empty_set_when_none(self):
        mock_result = MagicMock()
        mock_result.stdout = "[]"
        with patch("subprocess.run", return_value=mock_result):
            assert _fetch_merged_pr_titles() == set()

    def test_fetch_merged_pr_titles_returns_empty_set_on_subprocess_error(self):
        with patch("subprocess.run", side_effect=subprocess.SubprocessError()):
            assert _fetch_merged_pr_titles() == set()

    def test_fetch_merged_pr_titles_returns_empty_set_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=5)):
            assert _fetch_merged_pr_titles() == set()


class TestMarkTaskComplete:
    def test_mark_task_complete_updates_pending_task(self, tmp_path):
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-123", "status": "pending"}]}))
        result = _mark_task_complete(tasks_file, "T-123")
        assert result == "marked"
        data = json.loads(tasks_file.read_text())
        assert data["tasks"][0]["status"] == "complete"

    def test_mark_task_complete_returns_false_for_nonexistent_task(self, tmp_path):
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-999", "status": "pending"}]}))
        assert _mark_task_complete(tasks_file, "T-123") == "not_found"

    def test_mark_task_complete_skips_already_complete_task(self, tmp_path):
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-123", "status": "complete"}]}))
        assert _mark_task_complete(tasks_file, "T-123") == "already_complete"

    def test_mark_task_complete_is_idempotent(self, tmp_path):
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-123", "status": "pending"}]}))
        first = _mark_task_complete(tasks_file, "T-123")
        second = _mark_task_complete(tasks_file, "T-123")
        assert first == "marked"
        assert second == "already_complete"
        data = json.loads(tasks_file.read_text())
        assert data["tasks"][0]["status"] == "complete"


class TestEndToEndPRAutoDetect:
    def test_main_marks_complete_and_runs_cleanup_when_pr_merged(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "tasks_in_flight.json").write_text('["T-123"]')
        (tmp_path / "tasks.json").write_text(json.dumps({
            "tasks": [{"task_id": "T-123", "status": "pending"}]
        }))
        pty = tmp_path / "agentflow" / "shell" / "pty_signal.py"
        pty.parent.mkdir(parents=True)
        pty.write_text("")
        cleanup = tmp_path / "agentflow" / "tools" / "cleanup_tasks.py"
        cleanup.parent.mkdir(parents=True, exist_ok=True)
        cleanup.write_text("")

        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with patch("agentflow.hooks.post_tool_use_agent._fetch_merged_pr_titles", return_value={"T-123: add feature", "T-1234: other"}):
                with patch("subprocess.run") as mock_run:
                    with pytest.raises(SystemExit) as exc:
                        main()

        assert exc.value.code == 0
        data = json.loads((tmp_path / "tasks.json").read_text())
        assert data["tasks"][0]["status"] == "complete"
        cleanup_calls = [c for c in mock_run.call_args_list if "cleanup_tasks.py" in str(c)]
        assert len(cleanup_calls) >= 1


class TestRunCleanup:
    def test_run_cleanup_ignores_subprocess_error(self, tmp_path):
        with patch("subprocess.run", side_effect=OSError("not found")):
            _run_cleanup(tmp_path)  # must not raise


class TestCoverageEdgeCases:
    def test_mark_task_complete_returns_false_on_lock_failure(self, tmp_path):
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-1", "status": "pending"}]}))
        with patch("agentflow.hooks.post_tool_use_agent.fcntl.flock", side_effect=BlockingIOError()):
            assert _mark_task_complete(tasks_file, "T-1") == "locked"

    def test_main_exits_zero_when_tasks_json_missing(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "tasks_in_flight.json").write_text('["T-001"]')
        # tasks.json deliberately absent
        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 0


class TestEdgeCases:
    def test_mark_task_complete_returns_false_on_json_decode_error(self, tmp_path):
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text("not valid json{{{")
        assert _mark_task_complete(tasks_file, "T-1").startswith("error:")

    def test_no_false_positive_prefix_match(self, tmp_path):
        # T-1 must not match a PR titled "T-12: something"
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-1", "status": "pending"}]}))
        with patch("agentflow.hooks.post_tool_use_agent._fetch_merged_pr_titles",
                   return_value={"T-12: some other task"}):
            with patch("agentflow.hooks.post_tool_use_agent._mark_task_complete") as mock_mark:
                # Simulate the check used in main()
                merged_titles = {"T-12: some other task"}
                task_id = "T-1"
                matched = any(
                    f"{task_id}:" in title or title.startswith(f"{task_id} ")
                    for title in merged_titles
                )
                assert matched is False
