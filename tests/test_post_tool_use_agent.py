"""Tests for post_tool_use_agent hook."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentflow.hooks.post_tool_use_agent import (
    _fetch_merged_pr_titles,
    _mark_task_complete,
    _run_cleanup,
    main,
    _register_pr_url,
    _check_pr_state,
    _is_pr_merge_bash,
    _log,
)


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


class TestSplitCoverage:
    def test_fetch_merged_pr_titles_exception(self):
        with patch("subprocess.run", side_effect=Exception("gh error")):
            assert _fetch_merged_pr_titles() == set()

    def test_register_pr_url_happy(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        assert _register_pr_url(agentflow_dir, "T-100", "https://pr") is True
        assert (agentflow_dir / "task_prs.json").exists()

    def test_register_pr_url_exception(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        assert _register_pr_url(agentflow_dir, "T-100", "https://pr") is False

    def test_check_pr_state_merged(self):
        mock_run = MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = '{"state": "MERGED"}'
        with patch("subprocess.run", return_value=mock_run):
            assert _check_pr_state("https://pr") == "MERGED"

    def test_check_pr_state_exception(self):
        with patch("subprocess.run", side_effect=Exception("gh error")):
            assert _check_pr_state("https://pr") is None

    def test_is_pr_merge_bash(self):
        assert _is_pr_merge_bash({"tool_input": {"command": "gh pr merge 1"}}) is True
        assert _is_pr_merge_bash({"tool_input": {"command": "git status"}}) is False

    def test_log_exception(self, tmp_path):
        _log(tmp_path / "not-exists", {"event": "test"})

    def test_mark_task_complete_no_file(self, tmp_path):
        assert _mark_task_complete(tmp_path / "not_found.json", "T-101") == "not_found"

    def test_mark_task_complete_not_found(self, tmp_path):
        f = tmp_path / "tasks.json"
        f.write_text(json.dumps({"tasks": []}))
        assert _mark_task_complete(f, "T-101") == "not_found"

    def test_mark_task_complete_exception(self, tmp_path):
        assert _mark_task_complete(Path("/invalid_dir/tasks.json"), "T-101").startswith("error:")

    def test_run_cleanup_exception(self):
        with patch("subprocess.run", side_effect=Exception("cleanup error")):
            _run_cleanup(Path("/nonexistent"))

    def test_find_workspace_root_fallback(self, tmp_path):
        from agentflow.hooks.post_tool_use_agent import _find_workspace_root
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            with patch("pathlib.Path.is_dir", return_value=False):
                assert _find_workspace_root() == tmp_path

    def test_find_workspace_root_from_worktree(self, tmp_path):
        """When called from inside .claude/worktrees/, skip worktree .agentflow and return project root."""
        from agentflow.hooks.post_tool_use_agent import _find_workspace_root
        # Create project root with .agentflow
        (tmp_path / ".agentflow").mkdir()
        # Create worktree structure
        worktree_path = tmp_path / ".claude" / "worktrees" / "task-T-308"
        worktree_path.mkdir(parents=True)
        (worktree_path / ".agentflow").mkdir()

        # Call from worktree CWD
        with patch("pathlib.Path.cwd", return_value=worktree_path):
            result = _find_workspace_root()

        # Should return project root, not worktree
        assert result == tmp_path

    def test_find_workspace_root_from_project_root(self, tmp_path):
        """When called from project root with .agentflow present, return project root."""
        from agentflow.hooks.post_tool_use_agent import _find_workspace_root
        (tmp_path / ".agentflow").mkdir()

        with patch("pathlib.Path.cwd", return_value=tmp_path):
            result = _find_workspace_root()

        assert result == tmp_path

    def test_find_workspace_root_from_subdir(self, tmp_path):
        """When called from subdir of project root, return project root."""
        from agentflow.hooks.post_tool_use_agent import _find_workspace_root
        (tmp_path / ".agentflow").mkdir()
        subdir = tmp_path / "subdir" / "nested"
        subdir.mkdir(parents=True)

        with patch("pathlib.Path.cwd", return_value=subdir):
            result = _find_workspace_root()

        assert result == tmp_path

    def test_main_in_flight_file_missing(self, tmp_path):
        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 0

    def test_main_in_flight_corrupted(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "tasks_in_flight.json").write_text("not json")
        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 0

    def test_main_tasks_json_missing(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "tasks_in_flight.json").write_text('["T-100"]')
        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 0

    def test_main_tasks_json_corrupted(self, tmp_path):
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "tasks_in_flight.json").write_text('["T-100"]')
        (tmp_path / "tasks.json").write_text("not json")
        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 0


class TestT314:
    def test_scrub_secrets(self):
        from agentflow.hooks.post_tool_use_agent import _scrub_secrets
        assert _scrub_secrets("export PASSWORD=foo") == "export PASSWORD=******"
        assert _scrub_secrets("export API_KEY='bar'") == "export API_KEY=******"
        assert _scrub_secrets("my-tool --token abc") == "my-tool --token ******"
        assert _scrub_secrets("my-tool --db-password=xyz") == "my-tool --db-password=******"
        assert _scrub_secrets("echo normal") == "echo normal"

    def test_log_rotation(self, tmp_path):
        from agentflow.hooks.post_tool_use_agent import _rotate_log
        log_file = tmp_path / "test.jsonl"
        log_file.write_text("a" * 15)
        _rotate_log(log_file, max_size_bytes=10, backup_count=3)
        assert not log_file.exists()
        assert (tmp_path / "test.jsonl.1").exists()
        assert (tmp_path / "test.jsonl.1").read_text() == "a" * 15

        log_file.write_text("b" * 15)
        _rotate_log(log_file, max_size_bytes=10, backup_count=3)
        assert not log_file.exists()
        assert (tmp_path / "test.jsonl.1").read_text() == "b" * 15
        assert (tmp_path / "test.jsonl.2").read_text() == "a" * 15

    def test_main_logging(self, tmp_path):
        import io
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "tasks_in_flight.json").write_text("[]")
        (tmp_path / "tasks.json").write_text(json.dumps({"tasks": []}))
        (tmp_path / "agentflow" / "shell").mkdir(parents=True)
        # Test scrubbed
        hook_in = {"tool_name": "Bash", "tool_input": {"command": "python script.py --token=super-secret"}}
        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with patch("sys.stdin", io.StringIO(json.dumps(hook_in))):
                with pytest.raises(SystemExit):
                    main()
        log_f = agentflow_dir / "hook_drain_debug.jsonl"
        assert json.loads(log_f.read_text().splitlines()[-1])["cmd"] == "python script.py --token=******"
        # Test full command when secrets absent
        long_cmd = "echo " + "a" * 100
        hook_in = {"tool_name": "Bash", "tool_input": {"command": long_cmd}}
        with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
            with patch("sys.stdin", io.StringIO(json.dumps(hook_in))):
                with pytest.raises(SystemExit):
                    main()
        assert json.loads(log_f.read_text().splitlines()[-1])["cmd"] == long_cmd



