"""Tests for user_prompt_submit hook — task lifecycle and pty_signal integration."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentflow.hooks.ups_task_sync import _cleanup_merged_in_flight
from agentflow.hooks.user_prompt_submit import main


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

        with patch(
            "agentflow.hooks.ups_task_sync._fetch_merged_pr_titles",
            return_value={"feat(T-52): new feature"},
        ):
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
            with patch("agentflow.hooks.ups_task_sync.subprocess.run", return_value=mock_result) as mock_run:
                _cleanup_merged_in_flight(agentflow_dir, sid="s5")

        task_done_calls = [c for c in mock_run.call_args_list if "task_done" in str(c)]
        assert len(task_done_calls) >= 1
        cmd = task_done_calls[0][0][0]
        # First element must be sys.executable, not a shell string
        assert cmd[0] == sys.executable
        assert "shell" not in task_done_calls[0][1] or task_done_calls[0][1].get("shell") is not True


class TestUserPromptSubmitHookMain:
    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        # We need to mock sys.stdin.read to return json, and avoid real sys.exit
        self.mock_cleanup = patch("agentflow.hooks.user_prompt_submit._cleanup_merged_in_flight")
        self.mock_cleanup.start()
        yield
        self.mock_cleanup.stop()

    def test_orchestrate_writes_session_state(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
        monkeypatch.setenv("AGENTFLOW_SESSION_ID", "sess-orchestrate")
        
        session_dir = tmp_path / ".agentflow" / "sessions" / "sess-orchestrate"
        session_dir.mkdir(parents=True)
        
        # Test exact "/orchestrate" command
        with patch("agentflow.hooks.user_prompt_submit.sys.stdin") as mock_stdin,              patch("agentflow.hooks.user_prompt_submit.sys.argv", ["user_prompt_submit.py"]):
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps({"prompt": "/orchestrate"})
            
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 0
            
        state_file = session_dir / "session_state.json"
        assert state_file.exists()
        assert json.loads(state_file.read_text())["session_type"] == "orchestrator"

    def test_orchestrator_startup_writes_session_state(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
        monkeypatch.setenv("AGENTFLOW_SESSION_ID", "sess-orchestrator")
        
        session_dir = tmp_path / ".agentflow" / "sessions" / "sess-orchestrator"
        session_dir.mkdir(parents=True)
        
        # Test "/orchestrator:startup" command
        with patch("agentflow.hooks.user_prompt_submit.sys.stdin") as mock_stdin,              patch("agentflow.hooks.user_prompt_submit.sys.argv", ["user_prompt_submit.py"]):
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps({"prompt": "/orchestrator:startup"})
            
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 0
            
        state_file = session_dir / "session_state.json"
        assert state_file.exists()
        assert json.loads(state_file.read_text())["session_type"] == "orchestrator"

    def test_oracle_writes_session_state(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
        monkeypatch.setenv("AGENTFLOW_SESSION_ID", "sess-oracle")
        
        session_dir = tmp_path / ".agentflow" / "sessions" / "sess-oracle"
        session_dir.mkdir(parents=True)
        
        with patch("agentflow.hooks.user_prompt_submit.sys.stdin") as mock_stdin,              patch("agentflow.hooks.user_prompt_submit.sys.argv", ["user_prompt_submit.py"]):
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps({"prompt": "/oracle"})
            
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 0
            
        state_file = session_dir / "session_state.json"
        assert state_file.exists()
        assert json.loads(state_file.read_text())["session_type"] == "oracle"

    def test_handoff_clears_signal_files(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
        monkeypatch.setenv("AGENTFLOW_SESSION_ID", "sess-handoff")
        
        session_dir = tmp_path / ".agentflow" / "sessions" / "sess-handoff"
        session_dir.mkdir(parents=True)
        
        # Pre-create signal files
        handoff_file = session_dir / "handoff_complete.json"
        task_file = session_dir / "task_complete.json"
        handoff_file.write_text("{}")
        task_file.write_text("{}")
        
        with patch("agentflow.hooks.user_prompt_submit.sys.stdin") as mock_stdin,              patch("agentflow.hooks.user_prompt_submit.sys.argv", ["user_prompt_submit.py"]):
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps({"prompt": "/handoff"})
            
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 0
            
        assert not handoff_file.exists()
        assert not task_file.exists()

    def test_clear_creates_clear_signal(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
        
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir(parents=True)
        clear_signal = agentflow_dir / "clear_signal"
        
        with patch("agentflow.hooks.user_prompt_submit.sys.stdin") as mock_stdin,              patch("agentflow.hooks.user_prompt_submit.sys.argv", ["user_prompt_submit.py"]):
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps({"prompt": "/clear"})
            
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 0
            
        assert clear_signal.exists()

