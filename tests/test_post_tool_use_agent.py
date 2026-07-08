"""Tests for post_tool_use_agent hook."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from agentflow.hooks.post_tool_use_agent import _detect_merged_pr, _mark_task_complete, _run_cleanup, main


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


class TestNoOp:
    def test_exits_zero_when_no_in_flight_file(self, tmp_path):
        (tmp_path / ".agentflow").mkdir()
        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with patch("builtins.open", side_effect=FileNotFoundError):
                with pytest.raises(SystemExit) as exc:
                    main()
        assert exc.value.code == 0

    def test_exits_zero_when_in_flight_empty(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "tasks_in_flight.json").write_text("[]")
        (tmp_path / "tasks.json").write_text(json.dumps({"tasks": []}))
        (tmp_path / "agentflow" / "shell").mkdir(parents=True)

        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with patch("subprocess.run") as mock_run:
                with pytest.raises(SystemExit) as exc:
                    main()
        assert exc.value.code == 0
        mock_run.assert_not_called()


class TestSignalFiring:
    def test_calls_task_done_for_completed_in_flight_task(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "tasks_in_flight.json").write_text('["T-010", "T-020"]')
        (tmp_path / "tasks.json").write_text(json.dumps({
            "tasks": [
                {"task_id": "T-010", "status": "complete"},
                {"task_id": "T-020", "status": "pending"},
            ]
        }))
        pty = tmp_path / "agentflow" / "shell" / "pty_signal.py"
        pty.parent.mkdir(parents=True)
        pty.write_text("")

        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with patch("agentflow.hooks.post_tool_use_agent._detect_merged_pr", return_value=False):
                with patch("subprocess.run") as mock_run:
                    with pytest.raises(SystemExit) as exc:
                        main()

        assert exc.value.code == 0
        mock_run.assert_called_once_with(
            [sys.executable, str(pty), "task_done", "T-010"],
            check=False,
            capture_output=True,
        )

    def test_calls_task_done_for_all_non_pending_tasks(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "tasks_in_flight.json").write_text('["T-001", "T-002", "T-003"]')
        (tmp_path / "tasks.json").write_text(json.dumps({
            "tasks": [
                {"task_id": "T-001", "status": "complete"},
                {"task_id": "T-002", "status": "complete"},
                {"task_id": "T-003", "status": "pending"},
            ]
        }))
        pty = tmp_path / "agentflow" / "shell" / "pty_signal.py"
        pty.parent.mkdir(parents=True)
        pty.write_text("")

        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with patch("agentflow.hooks.post_tool_use_agent._detect_merged_pr", return_value=False):
                with patch("subprocess.run") as mock_run:
                    with pytest.raises(SystemExit) as exc:
                        main()

        assert exc.value.code == 0
        assert mock_run.call_count == 2
        called_task_ids = {c.args[0][-1] for c in mock_run.call_args_list}
        assert called_task_ids == {"T-001", "T-002"}

    def test_no_signal_when_all_tasks_still_pending(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "tasks_in_flight.json").write_text('["T-005"]')
        (tmp_path / "tasks.json").write_text(json.dumps({
            "tasks": [{"task_id": "T-005", "status": "pending"}]
        }))
        pty = tmp_path / "agentflow" / "shell" / "pty_signal.py"
        pty.parent.mkdir(parents=True)
        pty.write_text("")

        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with patch("agentflow.hooks.post_tool_use_agent._detect_merged_pr", return_value=False):
                with patch("subprocess.run") as mock_run:
                    with pytest.raises(SystemExit) as exc:
                        main()

        assert exc.value.code == 0
        mock_run.assert_not_called()


class TestInFlightReconciliation:
    def test_removes_completed_tasks_from_in_flight_file(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        in_flight_file = agentflow_dir / "tasks_in_flight.json"
        in_flight_file.write_text('["T-010", "T-020"]')
        (tmp_path / "tasks.json").write_text(json.dumps({
            "tasks": [
                {"task_id": "T-010", "status": "complete"},
                {"task_id": "T-020", "status": "pending"},
            ]
        }))
        pty = tmp_path / "agentflow" / "shell" / "pty_signal.py"
        pty.parent.mkdir(parents=True)
        pty.write_text("")

        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with patch("subprocess.run"):
                with pytest.raises(SystemExit):
                    main()

        assert json.loads(in_flight_file.read_text()) == ["T-020"]

    def test_clears_in_flight_file_when_all_complete(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        in_flight_file = agentflow_dir / "tasks_in_flight.json"
        in_flight_file.write_text('["T-001", "T-002"]')
        (tmp_path / "tasks.json").write_text(json.dumps({
            "tasks": [
                {"task_id": "T-001", "status": "complete"},
                {"task_id": "T-002", "status": "complete"},
            ]
        }))
        (tmp_path / "agentflow" / "shell").mkdir(parents=True)

        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with patch("subprocess.run"):
                with pytest.raises(SystemExit):
                    main()

        assert json.loads(in_flight_file.read_text()) == []

    def test_leaves_in_flight_unchanged_when_all_pending(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        in_flight_file = agentflow_dir / "tasks_in_flight.json"
        in_flight_file.write_text('["T-005"]')
        (tmp_path / "tasks.json").write_text(json.dumps({
            "tasks": [{"task_id": "T-005", "status": "pending"}]
        }))
        (tmp_path / "agentflow" / "shell").mkdir(parents=True)

        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with patch("subprocess.run"):
                with pytest.raises(SystemExit):
                    main()

        assert json.loads(in_flight_file.read_text()) == ["T-005"]


class TestRobustness:
    def test_subprocess_exception_does_not_crash_hook(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "tasks_in_flight.json").write_text('["T-007"]')
        (tmp_path / "tasks.json").write_text(json.dumps({
            "tasks": [{"task_id": "T-007", "status": "complete"}]
        }))
        (tmp_path / "agentflow" / "shell").mkdir(parents=True)

        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with patch("subprocess.run", side_effect=OSError("no such file")):
                with pytest.raises(SystemExit) as exc:
                    main()

        assert exc.value.code == 0

    def test_corrupted_tasks_json_exits_zero(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "tasks_in_flight.json").write_text('["T-009"]')
        (tmp_path / "tasks.json").write_text("NOT JSON")

        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with pytest.raises(SystemExit) as exc:
                main()

        assert exc.value.code == 0


class TestPRDetection:
    def test_detect_merged_pr_returns_true_when_gh_finds_pr(self):
        mock_result = MagicMock()
        mock_result.stdout = '[{"number": 42}]'
        with patch("subprocess.run", return_value=mock_result):
            assert _detect_merged_pr("T-123") is True

    def test_detect_merged_pr_returns_false_when_gh_finds_no_pr(self):
        mock_result = MagicMock()
        mock_result.stdout = "[]"
        with patch("subprocess.run", return_value=mock_result):
            assert _detect_merged_pr("T-123") is False

    def test_detect_merged_pr_returns_false_on_subprocess_error(self):
        with patch("subprocess.run", side_effect=subprocess.SubprocessError()):
            assert _detect_merged_pr("T-123") is False

    def test_detect_merged_pr_returns_false_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=5)):
            assert _detect_merged_pr("T-123") is False


class TestMarkTaskComplete:
    def test_mark_task_complete_updates_pending_task(self, tmp_path):
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-123", "status": "pending"}]}))
        result = _mark_task_complete(tasks_file, "T-123")
        assert result is True
        data = json.loads(tasks_file.read_text())
        assert data["tasks"][0]["status"] == "complete"

    def test_mark_task_complete_returns_false_for_nonexistent_task(self, tmp_path):
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-999", "status": "pending"}]}))
        assert _mark_task_complete(tasks_file, "T-123") is False

    def test_mark_task_complete_skips_already_complete_task(self, tmp_path):
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-123", "status": "complete"}]}))
        assert _mark_task_complete(tasks_file, "T-123") is False

    def test_mark_task_complete_is_idempotent(self, tmp_path):
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-123", "status": "pending"}]}))
        first = _mark_task_complete(tasks_file, "T-123")
        second = _mark_task_complete(tasks_file, "T-123")
        assert first is True
        assert second is False
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
            with patch("agentflow.hooks.post_tool_use_agent._detect_merged_pr", return_value=True):
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
            assert _mark_task_complete(tasks_file, "T-1") is False

    def test_main_exits_zero_when_tasks_json_missing(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "tasks_in_flight.json").write_text('["T-001"]')
        # tasks.json deliberately absent
        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 0
