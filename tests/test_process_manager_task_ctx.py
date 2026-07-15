import json
import os
import tempfile
from pathlib import Path
from unittest import mock
import pytest


def write_current_round(tmpdir, task_ctx=None):
    """Helper to write current_round.json with optional task_ctx."""
    agentflow_dir = tmpdir / ".agentflow"
    agentflow_dir.mkdir()
    current_round = {
        "task_ids": ["T-001"],
        "round_id": "round-1",
        "timestamp": "2024-01-01T00:00:00Z",
    }
    if task_ctx is not None:
        current_round["task_ctx"] = task_ctx
    (agentflow_dir / "current_round.json").write_text(json.dumps(current_round), encoding="utf-8")


def test_spawn_new_child_appends_task_ctx_when_present(tmpdir, monkeypatch):
    """Test that task_ctx is appended to command when present in current_round.json."""
    monkeypatch.chdir(tmpdir)

    task_ctx = {
        "task_id": "T-196",
        "title": "Test task",
        "deps": ["T-195"],
        "estimated_lines": 30,
    }
    write_current_round(tmpdir, task_ctx)

    # Mock PTY and os.execvp
    with mock.patch("pty.fork") as mock_fork, \
         mock.patch("os.execvp") as mock_execvp, \
         mock.patch("fcntl.fcntl") as mock_fcntl, \
         mock.patch("fcntl.ioctl"), \
         mock.patch("os.close"):

        # Return (0, 10) so child_pid == 0 and we enter the execvp path
        mock_fork.return_value = (0, 10)
        mock_fcntl.return_value = 0

        manager = mock.Mock()
        manager._pty = mock.Mock()
        manager._pty._command = ["claude", "code"]
        manager._pty.master_fd = None
        manager._just_restarted = True
        manager.session_type = "orchestrator"
        manager._on_session_exit = None
        manager._handle_output = None
        manager._log_audit = mock.Mock()

        from agentflow.shell.process_manager import spawn_new_child

        # Mock os._exit so it doesn't actually exit
        with mock.patch("os._exit"):
            spawn_new_child(manager)

        # Verify execvp was called with command including TASK_CTX
        assert mock_execvp.called
        called_args = mock_execvp.call_args[0]
        assert len(called_args[1]) >= 3
        assert "/orchestrate" in called_args[1]

        # Find the TASK_CTX argument
        task_ctx_arg = None
        for arg in called_args[1]:
            if arg.startswith("TASK_CTX:"):
                task_ctx_arg = arg
                break

        assert task_ctx_arg is not None, "TASK_CTX: argument not found in command"
        assert "task_id=T-196" in task_ctx_arg
        assert "title=Test task" in task_ctx_arg
        assert "deps=T-195" in task_ctx_arg
        assert "estimated_lines=30" in task_ctx_arg


def test_spawn_new_child_no_task_ctx_when_absent(tmpdir, monkeypatch):
    """Test that no TASK_CTX is appended when task_ctx is absent."""
    monkeypatch.chdir(tmpdir)

    write_current_round(tmpdir)  # No task_ctx

    with mock.patch("pty.fork") as mock_fork, \
         mock.patch("os.execvp") as mock_execvp, \
         mock.patch("fcntl.fcntl") as mock_fcntl, \
         mock.patch("fcntl.ioctl"), \
         mock.patch("os.close"), \
         mock.patch("os._exit"):

        # Return (0, 10) so child_pid == 0 and we enter the execvp path
        mock_fork.return_value = (0, 10)
        mock_fcntl.return_value = 0

        manager = mock.Mock()
        manager._pty = mock.Mock()
        manager._pty._command = ["claude", "code"]
        manager._pty.master_fd = None
        manager._just_restarted = True
        manager.session_type = "orchestrator"
        manager._on_session_exit = None
        manager._handle_output = None
        manager._log_audit = mock.Mock()

        from agentflow.shell.process_manager import spawn_new_child
        spawn_new_child(manager)

        called_args = mock_execvp.call_args[0]
        for arg in called_args[1]:
            assert not arg.startswith("TASK_CTX:"), f"Unexpected TASK_CTX in {called_args[1]}"


def test_spawn_new_child_no_task_ctx_when_malformed(tmpdir, monkeypatch):
    """Test that malformed task_ctx is silently ignored."""
    monkeypatch.chdir(tmpdir)

    # task_ctx is a string, not a dict
    agentflow_dir = tmpdir / ".agentflow"
    agentflow_dir.mkdir()
    current_round = {
        "task_ids": ["T-001"],
        "round_id": "round-1",
        "timestamp": "2024-01-01T00:00:00Z",
        "task_ctx": "bad_string",
    }
    (agentflow_dir / "current_round.json").write_text(json.dumps(current_round), encoding="utf-8")

    with mock.patch("pty.fork") as mock_fork, \
         mock.patch("os.execvp") as mock_execvp, \
         mock.patch("fcntl.fcntl") as mock_fcntl, \
         mock.patch("fcntl.ioctl"), \
         mock.patch("os.close"), \
         mock.patch("os._exit"):

        mock_fork.return_value = (0, 10)
        mock_fcntl.return_value = 0

        manager = mock.Mock()
        manager._pty = mock.Mock()
        manager._pty._command = ["claude", "code"]
        manager._pty.master_fd = None
        manager._just_restarted = True
        manager.session_type = "orchestrator"
        manager._on_session_exit = None
        manager._handle_output = None
        manager._log_audit = mock.Mock()

        from agentflow.shell.process_manager import spawn_new_child
        # Should not raise an exception
        spawn_new_child(manager)

        called_args = mock_execvp.call_args[0]
        for arg in called_args[1]:
            assert not arg.startswith("TASK_CTX:"), f"Unexpected TASK_CTX in {called_args[1]}"


def test_spawn_new_child_no_task_ctx_when_file_missing(tmpdir, monkeypatch):
    """Test that missing current_round.json is silently ignored."""
    monkeypatch.chdir(tmpdir)

    # Don't create current_round.json at all

    with mock.patch("pty.fork") as mock_fork, \
         mock.patch("os.execvp") as mock_execvp, \
         mock.patch("fcntl.fcntl") as mock_fcntl, \
         mock.patch("fcntl.ioctl"), \
         mock.patch("os.close"), \
         mock.patch("os._exit"):

        mock_fork.return_value = (0, 10)
        mock_fcntl.return_value = 0

        manager = mock.Mock()
        manager._pty = mock.Mock()
        manager._pty._command = ["claude", "code"]
        manager._pty.master_fd = None
        manager._just_restarted = True
        manager.session_type = "orchestrator"
        manager._on_session_exit = None
        manager._handle_output = None
        manager._log_audit = mock.Mock()

        from agentflow.shell.process_manager import spawn_new_child
        # Should not raise an exception
        spawn_new_child(manager)

        called_args = mock_execvp.call_args[0]
        for arg in called_args[1]:
            assert not arg.startswith("TASK_CTX:"), f"Unexpected TASK_CTX in {called_args[1]}"


def test_task_ctx_deps_none_when_empty(tmpdir, monkeypatch):
    """Test that empty deps list becomes 'NONE' in TASK_CTX."""
    monkeypatch.chdir(tmpdir)

    task_ctx = {
        "task_id": "T-196",
        "title": "X",
        "deps": [],
        "estimated_lines": 10,
    }
    write_current_round(tmpdir, task_ctx)

    with mock.patch("pty.fork") as mock_fork, \
         mock.patch("os.execvp") as mock_execvp, \
         mock.patch("fcntl.fcntl") as mock_fcntl, \
         mock.patch("fcntl.ioctl"), \
         mock.patch("os.close"), \
         mock.patch("os._exit"):

        # Return (0, 10) so child_pid == 0 and we enter the execvp path
        mock_fork.return_value = (0, 10)
        mock_fcntl.return_value = 0

        manager = mock.Mock()
        manager._pty = mock.Mock()
        manager._pty._command = ["claude", "code"]
        manager._pty.master_fd = None
        manager._just_restarted = True
        manager.session_type = "orchestrator"
        manager._on_session_exit = None
        manager._handle_output = None
        manager._log_audit = mock.Mock()

        from agentflow.shell.process_manager import spawn_new_child
        spawn_new_child(manager)

        called_args = mock_execvp.call_args[0]

        task_ctx_arg = None
        for arg in called_args[1]:
            if arg.startswith("TASK_CTX:"):
                task_ctx_arg = arg
                break

        assert task_ctx_arg is not None, "TASK_CTX: argument not found"
        assert "deps=NONE" in task_ctx_arg, f"Expected deps=NONE in {task_ctx_arg}"


def test_spawn_new_child_no_error_when_session_id_absent(tmpdir, monkeypatch):
    """Test that spawn_new_child doesn't error when session_id field is absent from current_round.json."""
    monkeypatch.chdir(tmpdir)

    # Write current_round.json with task_ctx but NO session_id field (legacy case)
    agentflow_dir = tmpdir / ".agentflow"
    agentflow_dir.mkdir()
    current_round = {
        "task_ids": ["T-001"],
        "round_id": "round-1",
        "timestamp": "2024-01-01T00:00:00Z",
        "task_ctx": {
            "task_id": "T-218",
            "title": "Test task without session_id",
            "deps": [],
            "estimated_lines": 15,
        }
    }
    (agentflow_dir / "current_round.json").write_text(json.dumps(current_round), encoding="utf-8")

    with mock.patch("pty.fork") as mock_fork, \
         mock.patch("os.execvp") as mock_execvp, \
         mock.patch("fcntl.fcntl") as mock_fcntl, \
         mock.patch("fcntl.ioctl"), \
         mock.patch("os.close"), \
         mock.patch("os._exit"):

        mock_fork.return_value = (0, 10)
        mock_fcntl.return_value = 0

        manager = mock.Mock()
        manager._pty = mock.Mock()
        manager._pty._command = ["claude", "code"]
        manager._pty.master_fd = None
        manager._just_restarted = True
        manager.session_type = "orchestrator"
        manager._on_session_exit = None
        manager._handle_output = None
        manager._log_audit = mock.Mock()

        from agentflow.shell.process_manager import spawn_new_child
        # Should not raise an exception
        spawn_new_child(manager)

        # Verify execvp was called (no exception)
        assert mock_execvp.called
        called_args = mock_execvp.call_args[0]

        # Verify TASK_CTX was still appended despite missing session_id
        task_ctx_arg = None
        for arg in called_args[1]:
            if arg.startswith("TASK_CTX:"):
                task_ctx_arg = arg
                break

        assert task_ctx_arg is not None, "TASK_CTX should still be present even without session_id"
        assert "task_id=T-218" in task_ctx_arg
