"""Tests for post_tool_use_agent hook."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from agentflow.hooks.post_tool_use_agent import (
    _fetch_merged_pr_titles,
    _handle_pr_merge,
    _mark_task_complete,
    _run_cleanup,
    main,
)


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
            with patch("agentflow.hooks.post_tool_use_agent._fetch_merged_pr_titles", return_value=set()):
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
            with patch("agentflow.hooks.post_tool_use_agent._fetch_merged_pr_titles", return_value=set()):
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
            with patch("agentflow.hooks.post_tool_use_agent._fetch_merged_pr_titles", return_value=set()):
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


class TestHandlePrMerge:
    def _make_workspace(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-99", "status": "pending"}]}))
        pty = tmp_path / "agentflow" / "shell" / "pty_signal.py"
        pty.parent.mkdir(parents=True)
        pty.write_text("")
        cleanup = tmp_path / "agentflow" / "tools" / "cleanup_tasks.py"
        cleanup.parent.mkdir(parents=True, exist_ok=True)
        cleanup.write_text("")
        return agentflow_dir, tasks_file

    def test_gh_pr_merge_extracts_pr_number_and_calls_gh_pr_view(self, tmp_path):
        agentflow_dir, tasks_file = self._make_workspace(tmp_path)
        in_flight = ["T-99"]
        cmd = "gh pr merge 42 --merge"
        gh_view_result = MagicMock()
        gh_view_result.returncode = 0
        gh_view_result.stdout = json.dumps(
            {"url": "https://github.com/o/r/pull/42", "title": "feat(T-99): something", "state": "OPEN"}
        )

        with patch("subprocess.run", return_value=gh_view_result) as mock_run:
            _handle_pr_merge(cmd, in_flight, agentflow_dir, tmp_path, tasks_file)

        calls = [str(c) for c in mock_run.call_args_list]
        assert any("gh" in c and "pr" in c and "view" in c and "42" in c for c in calls)

    def test_merged_state_triggers_mark_complete_and_task_done(self, tmp_path):
        agentflow_dir, tasks_file = self._make_workspace(tmp_path)
        in_flight = ["T-99"]
        cmd = "gh pr merge 42"
        gh_view_result = MagicMock()
        gh_view_result.returncode = 0
        gh_view_result.stdout = json.dumps(
            {"url": "https://github.com/o/r/pull/42", "title": "feat(T-99): add things", "state": "MERGED"}
        )

        with patch("subprocess.run", return_value=gh_view_result) as mock_run:
            _handle_pr_merge(cmd, in_flight, agentflow_dir, tmp_path, tasks_file)

        data = json.loads(tasks_file.read_text())
        assert data["tasks"][0]["status"] == "complete"
        task_done_calls = [c for c in mock_run.call_args_list if "task_done" in str(c)]
        assert len(task_done_calls) >= 1
        assert "T-99" in str(task_done_calls[0])

    def test_open_state_registers_pr_url(self, tmp_path):
        agentflow_dir, tasks_file = self._make_workspace(tmp_path)
        in_flight = ["T-99"]
        cmd = "gh pr merge 42 --auto"
        pr_url = "https://github.com/o/r/pull/42"
        gh_view_result = MagicMock()
        gh_view_result.returncode = 0
        gh_view_result.stdout = json.dumps(
            {"url": pr_url, "title": "feat(T-99): auto-merge", "state": "OPEN"}
        )

        with patch("subprocess.run", return_value=gh_view_result):
            _handle_pr_merge(cmd, in_flight, agentflow_dir, tmp_path, tasks_file)

        prs_file = agentflow_dir / "task_prs.json"
        assert prs_file.exists()
        prs = json.loads(prs_file.read_text())
        assert prs.get("T-99") == pr_url

    def test_no_pr_number_in_cmd_does_nothing(self, tmp_path):
        agentflow_dir, tasks_file = self._make_workspace(tmp_path)
        with patch("subprocess.run") as mock_run:
            _handle_pr_merge("some other command", [], agentflow_dir, tmp_path, tasks_file)
        mock_run.assert_not_called()

    def test_singleton_in_flight_fallback_when_title_has_no_task_id(self, tmp_path):
        agentflow_dir, tasks_file = self._make_workspace(tmp_path)
        in_flight = ["T-99"]
        cmd = "gh pr merge 7"
        gh_view_result = MagicMock()
        gh_view_result.returncode = 0
        gh_view_result.stdout = json.dumps(
            {"url": "https://github.com/o/r/pull/7", "title": "some title no task id", "state": "MERGED"}
        )

        with patch("subprocess.run", return_value=gh_view_result):
            _handle_pr_merge(cmd, in_flight, agentflow_dir, tmp_path, tasks_file)

        data = json.loads(tasks_file.read_text())
        assert data["tasks"][0]["status"] == "complete"

    def test_handle_pr_merge_multi_pr(self, tmp_path):
        """Test that gh pr merge 148 149 processes both PR numbers."""
        agentflow_dir, tasks_file = self._make_workspace(tmp_path)
        in_flight = ["T-99"]
        cmd = "gh pr merge 148 149"

        # Mock gh pr view to return MERGED for both PRs
        gh_view_result = MagicMock()
        gh_view_result.returncode = 0
        gh_view_result.stdout = json.dumps(
            {"url": "https://github.com/o/r/pull/148", "title": "feat(T-99): first", "state": "MERGED"}
        )

        call_count = 0
        def mock_run_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Return MERGED for gh pr view calls
            if "pr" in args[0] and "view" in args[0]:
                pr_num = args[0][args[0].index("view") + 1]
                result = MagicMock()
                result.returncode = 0
                result.stdout = json.dumps({
                    "url": f"https://github.com/o/r/pull/{pr_num}",
                    "title": f"feat(T-99): pr{pr_num}",
                    "state": "MERGED"
                })
                return result
            # Return ok for task_done calls
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        with patch("subprocess.run", side_effect=mock_run_side_effect) as mock_run:
            _handle_pr_merge(cmd, in_flight, agentflow_dir, tmp_path, tasks_file)

        # Should have called gh pr view for both PRs (148 and 149)
        view_calls = [c for c in mock_run.call_args_list if len(c[0]) > 0 and "view" in str(c[0])]
        assert len(view_calls) >= 2, f"Expected at least 2 gh pr view calls, got {len(view_calls)}"


class TestDrainEvents:
    """Test drain event logging in main()."""

    def test_main_emits_drain_start_and_complete(self, tmp_path):
        """Test that main() emits drain_start and drain_complete events."""
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "tasks_in_flight.json").write_text(json.dumps(["T-237"]))
        (tmp_path / "tasks.json").write_text(json.dumps({
            "tasks": [{"task_id": "T-237", "status": "complete"}]
        }))
        pty = tmp_path / "agentflow" / "shell" / "pty_signal.py"
        pty.parent.mkdir(parents=True)
        pty.write_text("")

        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with patch("agentflow.hooks.post_tool_use_agent._fetch_merged_pr_titles", return_value=set()):
                with patch("subprocess.run") as mock_run:
                    with pytest.raises(SystemExit) as exc:
                        main()

        assert exc.value.code == 0

        # Read the debug log to verify drain events
        debug_log = agentflow_dir / "hook_drain_debug.jsonl"
        assert debug_log.exists(), f"Debug log not created at {debug_log}"
        events = []
        for line in debug_log.read_text().strip().split("\n"):
            if line:
                events.append(json.loads(line))

        event_names = [e.get("event") for e in events]
        assert "drain_start" in event_names, f"Expected drain_start event, got events: {event_names}"
        assert "drain_complete" in event_names, f"Expected drain_complete event, got events: {event_names}"

        # Verify drain_complete has elapsed time and task count
        complete_events = [e for e in events if e.get("event") == "drain_complete"]
        assert len(complete_events) > 0, "No drain_complete events found"
        complete = complete_events[0]
        assert "elapsed" in complete, f"drain_complete missing elapsed time: {complete}"
        assert "completed_count" in complete, f"drain_complete missing completed_count: {complete}"
        assert complete["completed_count"] == 1, f"Expected 1 completed task, got {complete['completed_count']}"
