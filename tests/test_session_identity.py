"""Tests for T-106: PTY session identity and tracking."""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import uuid
from unittest.mock import MagicMock, patch

import pytest

from agentflow.cli import cmd_shell
from agentflow.shell.session_manager import SessionManager


class FakePTY:
    def __init__(self):
        self._on_output = None
        self._on_exit = None
        self.inputs: list[str] = []

    def write_input(self, text: str) -> None:
        self.inputs.append(text)

    def read_output(self, timeout: float = 1.0) -> bytes:
        return b""


class FakeTokenizer:
    def __init__(self):
        self._total = 0

    def count_tokens(self, text: str, provider: str = "claude") -> int:
        return 1

    def accumulate(self, text: str, provider: str = "claude") -> int:
        self._total += 1
        return self._total


def test_uuid_generation_and_session_json_writing(tmp_path):
    """Verify that cmd_shell sets AGENTFLOW_SESSION_ID env var and writes the session JSON."""
    home_dir = tmp_path / "home"
    cwd_dir = tmp_path / "cwd"
    home_dir.mkdir()
    cwd_dir.mkdir()

    # Pre-create the .agentflow directory in cwd and write an arm file
    af_dir = cwd_dir / ".agentflow"
    af_dir.mkdir()
    (af_dir / "verbosity_ab_arm.txt").write_text("on", encoding="utf-8")

    # Arguments for cmd_shell
    args = MagicMock()
    args.shell_command = "claude"

    # Mocks for select, termios, tty, sys.stdin/stdout
    mock_wrapper = MagicMock()
    mock_wrapper._exited = True
    mock_wrapper._exit_code = 0
    mock_wrapper.master_fd = 0
    mock_wrapper.read_output.return_value = b""

    # Clear target env var first
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AGENTFLOW_SESSION_ID", None)

        with patch("pathlib.Path.home", return_value=home_dir), \
             patch("pathlib.Path.cwd", return_value=cwd_dir), \
             patch("os.getcwd", return_value=str(cwd_dir)), \
             patch("sys.stdin.fileno", return_value=0), \
             patch("termios.tcgetattr", return_value=[]), \
             patch("tty.setraw"), \
             patch("termios.tcsetattr"), \
             patch("select.select", return_value=([], [], [])), \
             patch("sys.exit"), \
             patch("agentflow.shell.pty_shell.ProxyShell"), \
             patch("agentflow.shell.pty_wrapper.PTYWrapper", return_value=mock_wrapper):

            cmd_shell(args)

        # 1. Verify environment variable is set
        session_id = os.environ.get("AGENTFLOW_SESSION_ID")
        assert session_id is not None
        # Verify it's a valid UUID
        assert uuid.UUID(session_id)

        # 2. Verify the session JSON file is written
        session_file = home_dir / ".agentflow" / "sessions" / f"{session_id}.json"
        assert session_file.exists()

        data = json.loads(session_file.read_text(encoding="utf-8"))
        assert data["arm"] == "on"
        assert data["session_type"] is None
        assert "started_at" in data


def test_cli_shell_mkdir_exception(tmp_path):
    """Verify that cmd_shell handles exceptions during session folder creation gracefully."""
    home_dir = tmp_path / "home"
    cwd_dir = tmp_path / "cwd"
    home_dir.mkdir()
    cwd_dir.mkdir()

    af_dir = cwd_dir / ".agentflow"
    af_dir.mkdir()

    args = MagicMock()
    args.shell_command = "claude"

    mock_wrapper = MagicMock()
    mock_wrapper._exited = True
    mock_wrapper._exit_code = 0
    mock_wrapper.master_fd = 0
    mock_wrapper.read_output.return_value = b""

    original_mkdir = pathlib.Path.mkdir
    def mock_mkdir(self, *args, **kwargs):
        if "home" in self.parts and "sessions" in self.parts and self.name == "sessions":
            raise OSError("Permission denied")
        return original_mkdir(self, *args, **kwargs)

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AGENTFLOW_SESSION_ID", None)

        # Mock mkdir to raise exception to cover the try-except in cli.py
        with patch("pathlib.Path.home", return_value=home_dir), \
             patch("pathlib.Path.cwd", return_value=cwd_dir), \
             patch("os.getcwd", return_value=str(cwd_dir)), \
             patch("sys.stdin.fileno", return_value=0), \
             patch("termios.tcgetattr", return_value=[]), \
             patch("tty.setraw"), \
             patch("termios.tcsetattr"), \
             patch("select.select", return_value=([], [], [])), \
             patch("sys.exit"), \
             patch("agentflow.shell.pty_shell.ProxyShell"), \
             patch("pathlib.Path.mkdir", autospec=True, side_effect=mock_mkdir), \
             patch("agentflow.shell.pty_wrapper.PTYWrapper", return_value=mock_wrapper):

            # Should not raise exception
            cmd_shell(args)


def test_session_type_updates_inside_session_manager(tmp_path):
    """Verify that session_type updates inside SessionManager update the session file."""
    home_dir = tmp_path / "home"
    cwd_dir = tmp_path / "cwd"
    home_dir.mkdir()
    cwd_dir.mkdir()

    session_id = str(uuid.uuid4())
    sessions_dir = home_dir / ".agentflow" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_file = sessions_dir / f"{session_id}.json"

    # Write initial session file
    session_file.write_text(json.dumps({
        "arm": "off",
        "session_type": None,
        "started_at": "2026-07-04T12:00:00"
    }), encoding="utf-8")

    agentflow_dir = cwd_dir / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)
    sid_state_file = agentflow_dir / "sessions" / session_id / "session_state.json"
    sid_state_file.parent.mkdir(parents=True, exist_ok=True)

    pty = FakePTY()
    tok = FakeTokenizer()

    with patch.dict(os.environ, {"AGENTFLOW_SESSION_ID": session_id}), \
         patch("pathlib.Path.home", return_value=home_dir), \
         patch("pathlib.Path.cwd", return_value=cwd_dir), \
         patch("os.getcwd", return_value=str(cwd_dir)):

        sm = SessionManager(pty, tok, config={})
        assert sm.session_type is None

        # Simulate update to oracle by writing to the SID session state file
        sid_state_file.write_text(json.dumps({"session_type": "oracle"}), encoding="utf-8")
        sm._sync_session_type()
        assert sm.session_type == "oracle"

        # Check file was updated
        data = json.loads(session_file.read_text(encoding="utf-8"))
        assert data["session_type"] == "oracle"

        # Simulate output triggering clear via clear_signal file
        (agentflow_dir / "clear_signal").touch()
        pty._on_output(b"some clear output\n")
        assert sm.session_type is None

        data = json.loads(session_file.read_text(encoding="utf-8"))
        assert data["session_type"] is None

        # Simulate update to orchestrator by writing to the SID session state file
        sid_state_file.write_text(json.dumps({"session_type": "orchestrator"}), encoding="utf-8")
        sm._sync_session_type()
        assert sm.session_type == "orchestrator"

        data = json.loads(session_file.read_text(encoding="utf-8"))
        assert data["session_type"] == "orchestrator"


def test_update_session_file_no_existing_file(tmp_path):
    """Verify update session file when no session file exists initially."""
    home_dir = tmp_path / "home"
    cwd_dir = tmp_path / "cwd"
    home_dir.mkdir()
    cwd_dir.mkdir()

    session_id = str(uuid.uuid4())
    pty = FakePTY()
    tok = FakeTokenizer()

    with patch.dict(os.environ, {"AGENTFLOW_SESSION_ID": session_id}), \
         patch("pathlib.Path.home", return_value=home_dir), \
         patch("pathlib.Path.cwd", return_value=cwd_dir), \
         patch("os.getcwd", return_value=str(cwd_dir)):

        sm = SessionManager(pty, tok, config={})
        sm.session_type = "oracle"
        sm._update_session_file()

        session_file = home_dir / ".agentflow" / "sessions" / f"{session_id}.json"
        assert session_file.exists()
        data = json.loads(session_file.read_text(encoding="utf-8"))
        assert data["session_type"] == "oracle"
        assert "started_at" in data


def test_update_session_file_invalid_json(tmp_path):
    """Verify update session file when the existing file has invalid JSON content."""
    home_dir = tmp_path / "home"
    cwd_dir = tmp_path / "cwd"
    home_dir.mkdir()
    cwd_dir.mkdir()

    session_id = str(uuid.uuid4())
    sessions_dir = home_dir / ".agentflow" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_file = sessions_dir / f"{session_id}.json"
    session_file.write_text("invalid json string", encoding="utf-8")

    pty = FakePTY()
    tok = FakeTokenizer()

    with patch.dict(os.environ, {"AGENTFLOW_SESSION_ID": session_id}), \
         patch("pathlib.Path.home", return_value=home_dir), \
         patch("pathlib.Path.cwd", return_value=cwd_dir), \
         patch("os.getcwd", return_value=str(cwd_dir)):

        sm = SessionManager(pty, tok, config={})
        sm.session_type = "orchestrator"
        sm._update_session_file()

        assert session_file.exists()
        data = json.loads(session_file.read_text(encoding="utf-8"))
        assert data["session_type"] == "orchestrator"
        assert "started_at" in data


def test_update_session_file_write_exception(tmp_path):
    """Verify update session file handles exceptions gracefully (e.g. read-only system)."""
    home_dir = tmp_path / "home"
    cwd_dir = tmp_path / "cwd"
    home_dir.mkdir()
    cwd_dir.mkdir()

    session_id = str(uuid.uuid4())
    pty = FakePTY()
    tok = FakeTokenizer()

    with patch.dict(os.environ, {"AGENTFLOW_SESSION_ID": session_id}), \
         patch("pathlib.Path.home", return_value=home_dir), \
         patch("pathlib.Path.cwd", return_value=cwd_dir), \
         patch("os.getcwd", return_value=str(cwd_dir)):

        sm = SessionManager(pty, tok, config={})
        
        # Patch write_text to raise exception
        with patch("pathlib.Path.write_text", side_effect=OSError("Read-only file system")):
            # Should not raise exception
            sm._update_session_file()


def test_session_id_recorded_in_verbosity_log_entries(tmp_path):
    """Verify that session_id is recorded in verbosity_log.jsonl entries."""
    cwd_dir = tmp_path / "cwd"
    cwd_dir.mkdir()
    af_dir = cwd_dir / ".agentflow"
    af_dir.mkdir()

    session_id = str(uuid.uuid4())
    pty = FakePTY()
    tok = FakeTokenizer()

    with patch.dict(os.environ, {"AGENTFLOW_SESSION_ID": session_id}), \
         patch("pathlib.Path.cwd", return_value=cwd_dir), \
         patch("os.getcwd", return_value=str(cwd_dir)):

        sm = SessionManager(pty, tok, config={})
        sm.session_type = "oracle"

        # Trigger a normal turn boundary write to verbosity_log.jsonl
        pty._on_output(b"some response")
        sm._task_start_tokens = {"T-001": 0}
        pty._on_output(b"AGENTFLOW_TASK_COMPLETE:T-001\n")

        log_path = af_dir / "verbosity_log.jsonl"
        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["session_id"] == session_id
        assert record["session_type"] == "oracle"

        # Trigger a second turn boundary write — session_id must persist across turns
        pty._on_output(b"second response")
        sm._task_start_tokens = {"T-002": 0}
        pty._on_output(b"AGENTFLOW_TASK_COMPLETE:T-002\n")

        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        record2 = json.loads(lines[1])
        assert record2["session_id"] == session_id
        assert record2["session_type"] == "oracle"


def test_restart_session(tmp_path):
    """Verify _restart_session restarts the child process with the correct positional arguments."""
    import pty as pty_module
    from agentflow.shell.process_manager import spawn_new_child

    pty = FakePTY()
    pty._command = ["claude"]
    tok = FakeTokenizer()
    sm = SessionManager(pty, tok, config={})
    sm._project_root = tmp_path

    # 1. Oracle restart
    sm.session_type = "oracle"
    sm._just_restarted = True
    exec_called = []
    with patch.object(pty_module, "fork", return_value=(0, 123)), \
         patch("os.execvp", side_effect=lambda cmd, args: exec_called.append(args) or (_ for _ in ()).throw(SystemExit(127))), \
         patch("os._exit"):
        try:
            spawn_new_child(sm)
        except SystemExit:
            pass
    assert exec_called and exec_called[0] == ["claude", "/claude:oracle"]

    # 2. Orchestrator restart
    sm.session_type = "orchestrator"
    sm._just_restarted = True
    exec_called = []
    with patch.object(pty_module, "fork", return_value=(0, 123)), \
         patch("os.execvp", side_effect=lambda cmd, args: exec_called.append(args) or (_ for _ in ()).throw(SystemExit(127))), \
         patch("os._exit"):
        try:
            spawn_new_child(sm)
        except SystemExit:
            pass
    assert exec_called and exec_called[0] == ["claude", "/claude:orchestrate", "--permission-mode", "auto"]
