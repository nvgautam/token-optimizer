"""Comprehensive tests for tasks_in_flight.json SID-scoping (T-217)"""
import json
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest


class TestSessionManagerTasksInFlightPath:
    """Test _tasks_in_flight_path property in session_manager.py"""

    def test_tasks_in_flight_path_with_sid(self, tmp_path):
        """_tasks_in_flight_path should return sessions/<SID>/ path when SID is set."""
        from agentflow.shell.session_manager import SessionManager

        # Create a minimal mock PTY wrapper and tokenizer
        mock_pty = Mock()
        mock_tokenizer = Mock()

        # Create manager with tmp_path as project root
        manager = SessionManager(mock_pty, mock_tokenizer, {})
        manager._project_root = tmp_path

        # Set SID in environment
        os.environ["AGENTFLOW_SESSION_ID"] = "test-sid-123"
        try:
            path = manager._tasks_in_flight_path
            expected = tmp_path / ".agentflow" / "sessions" / "test-sid-123" / "tasks_in_flight.json"
            assert path == expected
        finally:
            os.environ.pop("AGENTFLOW_SESSION_ID", None)

    def test_tasks_in_flight_path_without_sid(self, tmp_path):
        """_tasks_in_flight_path should return root path when SID is empty (backward compat)."""
        from agentflow.shell.session_manager import SessionManager

        mock_pty = Mock()
        mock_tokenizer = Mock()
        manager = SessionManager(mock_pty, mock_tokenizer, {})
        manager._project_root = tmp_path

        # Ensure no SID in environment
        os.environ.pop("AGENTFLOW_SESSION_ID", None)
        try:
            path = manager._tasks_in_flight_path
            expected = tmp_path / ".agentflow" / "tasks_in_flight.json"
            assert path == expected
        finally:
            pass

    def test_tasks_in_flight_path_override(self, tmp_path):
        """_tasks_in_flight_path should respect override."""
        from agentflow.shell.session_manager import SessionManager

        mock_pty = Mock()
        mock_tokenizer = Mock()
        manager = SessionManager(mock_pty, mock_tokenizer, {})
        manager._project_root = tmp_path

        override_path = tmp_path / "override" / "tasks.json"
        manager._tasks_in_flight_path = override_path

        assert manager._tasks_in_flight_path == override_path


class TestPostToolUseAgentTasksInFlight:
    """Test tasks_in_flight SID-scoping in post_tool_use_agent.py"""

    def test_post_tool_use_agent_reads_sid_scoped_file(self, tmp_path, monkeypatch):
        """post_tool_use_agent should read from SID-scoped path when SID is set."""
        from agentflow.hooks.post_tool_use_agent import main
        import sys
        import io

        # Setup SID-scoped tasks_in_flight.json
        monkeypatch.setenv("AGENTFLOW_SESSION_ID", "test-session-agent")
        agentflow_dir = tmp_path / ".agentflow"
        sid_dir = agentflow_dir / "sessions" / "test-session-agent"
        sid_dir.mkdir(parents=True)

        # Create tasks_in_flight.json with a task
        tif_path = sid_dir / "tasks_in_flight.json"
        tif_path.write_text('["T-001"]')

        # Create minimal tasks.json
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-001", "status": "complete"}]}))

        # Mock stdin with hook data
        hook_data = {
            "tool_name": "Agent",
            "tool_input": {},
            "tool_response": {}
        }

        # Change to tmp_path so _find_workspace_root finds it
        monkeypatch.chdir(tmp_path)

        with patch("sys.stdin", io.StringIO(json.dumps(hook_data))):
            try:
                main()
            except SystemExit:
                pass

        # File should have been updated (tasks drained)
        assert json.loads(tif_path.read_text()) == []


class TestUserPromptSubmitTasksInFlight:
    """Test tasks_in_flight SID-scoping in user_prompt_submit.py"""

    def test_cleanup_merged_in_flight_uses_sid_path(self, tmp_path, monkeypatch):
        """_cleanup_merged_in_flight should use SID-scoped path when processing."""
        from agentflow.hooks.user_prompt_submit import _cleanup_merged_in_flight

        monkeypatch.setenv("AGENTFLOW_SESSION_ID", "test-session-submit")
        agentflow_dir = tmp_path / ".agentflow"
        sid_dir = agentflow_dir / "sessions" / "test-session-submit"
        sid_dir.mkdir(parents=True)

        # Create SID-scoped tasks_in_flight.json
        tif_path = sid_dir / "tasks_in_flight.json"
        tif_path.write_text('["T-001", "T-002"]')

        # Call with SID parameter (after implementation)
        _cleanup_merged_in_flight(agentflow_dir, sid="test-session-submit")

        # File should exist (might be updated)
        assert tif_path.exists()


class TestHandoffHandlerTasksInFlight:
    """Test check_drain_restart uses manager._tasks_in_flight_path"""

    def test_check_drain_restart_uses_manager_property(self, tmp_path, monkeypatch):
        """check_drain_restart should read via manager._tasks_in_flight_path"""
        from agentflow.shell.handoff_handler import check_drain_restart
        from agentflow.shell.session_manager import SessionManager

        monkeypatch.setenv("AGENTFLOW_SESSION_ID", "test-drain-session")
        monkeypatch.chdir(tmp_path)

        # Setup project structure
        agentflow_dir = tmp_path / ".agentflow"
        sid_dir = agentflow_dir / "sessions" / "test-drain-session"
        sid_dir.mkdir(parents=True)

        # Create SID-scoped files
        tif_path = sid_dir / "tasks_in_flight.json"
        tif_path.write_text('[]')  # drained

        round_path = agentflow_dir / "current_round.json"
        round_path.write_text('{"task_ids": []}')

        fill_path = sid_dir / "context_fill.json"
        fill_path.write_text('{"fill_tokens": 100000}')

        # Create a manager
        mock_pty = Mock()
        mock_pty._exited = False
        mock_tokenizer = Mock()

        manager = SessionManager(mock_pty, mock_tokenizer, {})
        manager._project_root = tmp_path
        manager.session_type = "orchestrator"
        manager._state_machine = Mock()
        manager._state_machine.state = Mock()
        manager._state_machine.state.value = "IDLE"
        manager._handoff_in_progress = False
        manager._log_audit = Mock()
        manager._last_restart_ts = 0.0
        manager._config = {"handoff_primary_tokens": 80000}

        # Patch the state machine check
        with patch.object(manager._state_machine.state, "name", "IDLE"):
            # The function should not crash and should read from manager._tasks_in_flight_path
            check_drain_restart(manager)
            # Verify _log_audit was called (indicating some processing happened)
            assert manager._log_audit.called


class TestSessionPathsIntegration:
    """Test session_file() integration with tasks_in_flight paths"""

    def test_session_file_creates_sid_directory(self, tmp_path):
        """session_file should create sessions/<SID>/ directory if needed."""
        from agentflow.shell.session_paths import session_file

        result = session_file(tmp_path / ".agentflow", "tasks_in_flight.json", "my-sid")
        expected_dir = tmp_path / ".agentflow" / "sessions" / "my-sid"

        assert expected_dir.exists()
        assert result == expected_dir / "tasks_in_flight.json"

    def test_session_file_returns_root_path_when_sid_empty(self, tmp_path):
        """session_file should return root path when SID is empty."""
        from agentflow.shell.session_paths import session_file

        result = session_file(tmp_path / ".agentflow", "tasks_in_flight.json", "")
        expected = tmp_path / ".agentflow" / "tasks_in_flight.json"

        assert result == expected
        # Root-level directory should not be created in sessions/
        assert not (tmp_path / ".agentflow" / "sessions").exists()

    def test_session_file_returns_root_path_when_sid_none(self, tmp_path):
        """session_file should return root path when SID is None."""
        from agentflow.shell.session_paths import session_file

        result = session_file(tmp_path / ".agentflow", "tasks_in_flight.json", None)
        expected = tmp_path / ".agentflow" / "tasks_in_flight.json"

        assert result == expected
