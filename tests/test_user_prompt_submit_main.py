"""Tests for user_prompt_submit hook — main() session state and signal file handling."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agentflow.hooks.user_prompt_submit import main


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

    # T-329: namespaced slash command tests

    def _run_main_with_prompt(self, tmp_path, monkeypatch, prompt: str, sid: str):
        """Helper: run main() with given prompt and return the agentflow sessions dir."""
        monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
        monkeypatch.setenv("AGENTFLOW_SESSION_ID", sid)
        session_dir = tmp_path / ".agentflow" / "sessions" / sid
        session_dir.mkdir(parents=True)
        with patch("agentflow.hooks.user_prompt_submit.sys.stdin") as mock_stdin, \
             patch("agentflow.hooks.user_prompt_submit.sys.argv", ["user_prompt_submit.py"]):
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps({"prompt": prompt})
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        return session_dir

    def test_namespaced_claude_orchestrate_writes_orchestrator(self, tmp_path, monkeypatch):
        """/claude:orchestrate → session_type = orchestrator."""
        sid = "sess-ns-orch"
        session_dir = self._run_main_with_prompt(tmp_path, monkeypatch, "/claude:orchestrate", sid)
        state_file = session_dir / "session_state.json"
        assert state_file.exists()
        assert json.loads(state_file.read_text())["session_type"] == "orchestrator"

    def test_namespaced_orchestrator_startup_writes_orchestrator(self, tmp_path, monkeypatch):
        """/orchestrator:startup → session_type = orchestrator."""
        sid = "sess-ns-startup"
        session_dir = self._run_main_with_prompt(tmp_path, monkeypatch, "/orchestrator:startup", sid)
        state_file = session_dir / "session_state.json"
        assert state_file.exists()
        assert json.loads(state_file.read_text())["session_type"] == "orchestrator"

    def test_namespaced_claude_oracle_writes_oracle(self, tmp_path, monkeypatch):
        """/claude:oracle → session_type = oracle."""
        sid = "sess-ns-oracle"
        session_dir = self._run_main_with_prompt(tmp_path, monkeypatch, "/claude:oracle", sid)
        state_file = session_dir / "session_state.json"
        assert state_file.exists()
        assert json.loads(state_file.read_text())["session_type"] == "oracle"

    def test_namespaced_claude_orchestrate_deletes_signal_files(self, tmp_path, monkeypatch):
        """/claude:orchestrate → handoff_complete.json and task_complete.json deleted."""
        sid = "sess-ns-del"
        monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
        monkeypatch.setenv("AGENTFLOW_SESSION_ID", sid)
        session_dir = tmp_path / ".agentflow" / "sessions" / sid
        session_dir.mkdir(parents=True)
        handoff_file = session_dir / "handoff_complete.json"
        task_file = session_dir / "task_complete.json"
        handoff_file.write_text("{}")
        task_file.write_text("{}")
        with patch("agentflow.hooks.user_prompt_submit.sys.stdin") as mock_stdin, \
             patch("agentflow.hooks.user_prompt_submit.sys.argv", ["user_prompt_submit.py"]):
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps({"prompt": "/claude:orchestrate"})
            with pytest.raises(SystemExit):
                main()
        assert not handoff_file.exists()
        assert not task_file.exists()

    def test_namespaced_claude_handoff_deletes_signal_files(self, tmp_path, monkeypatch):
        """/claude:handoff → handoff_complete.json and task_complete.json deleted."""
        sid = "sess-ns-handoff"
        monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
        monkeypatch.setenv("AGENTFLOW_SESSION_ID", sid)
        session_dir = tmp_path / ".agentflow" / "sessions" / sid
        session_dir.mkdir(parents=True)
        handoff_file = session_dir / "handoff_complete.json"
        task_file = session_dir / "task_complete.json"
        handoff_file.write_text("{}")
        task_file.write_text("{}")
        with patch("agentflow.hooks.user_prompt_submit.sys.stdin") as mock_stdin, \
             patch("agentflow.hooks.user_prompt_submit.sys.argv", ["user_prompt_submit.py"]):
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps({"prompt": "/claude:handoff"})
            with pytest.raises(SystemExit):
                main()
        assert not handoff_file.exists()
        assert not task_file.exists()

    def test_plain_orchestrate_regression(self, tmp_path, monkeypatch):
        """/orchestrate still works after namespaced command support."""
        sid = "sess-plain-orch"
        session_dir = self._run_main_with_prompt(tmp_path, monkeypatch, "/orchestrate", sid)
        state_file = session_dir / "session_state.json"
        assert state_file.exists()
        assert json.loads(state_file.read_text())["session_type"] == "orchestrator"

    def test_plain_oracle_regression(self, tmp_path, monkeypatch):
        """/oracle still works after namespaced command support."""
        sid = "sess-plain-oracle"
        session_dir = self._run_main_with_prompt(tmp_path, monkeypatch, "/oracle", sid)
        state_file = session_dir / "session_state.json"
        assert state_file.exists()
        assert json.loads(state_file.read_text())["session_type"] == "oracle"

    def test_orchestrator_tool_lookalike_does_not_trigger(self, tmp_path, monkeypatch):
        """/my-orchestrator-tool should NOT set session_type (exact-match guard)."""
        sid = "sess-lookalike"
        monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
        monkeypatch.setenv("AGENTFLOW_SESSION_ID", sid)
        session_dir = tmp_path / ".agentflow" / "sessions" / sid
        session_dir.mkdir(parents=True)
        with patch("agentflow.hooks.user_prompt_submit.sys.stdin") as mock_stdin, \
             patch("agentflow.hooks.user_prompt_submit.sys.argv", ["user_prompt_submit.py"]):
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps({"prompt": "/my-orchestrator-tool"})
            with pytest.raises(SystemExit):
                main()
        state_file = session_dir / "session_state.json"
        assert not state_file.exists()
