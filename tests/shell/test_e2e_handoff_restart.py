"""E2E test: handoff→restart cycle using a real PTY process.

Tests the full state machine cycle: IDLE → HANDOFF_PENDING → RESTARTING → IDLE
with a real PTY child process and callback injection.
"""
from __future__ import annotations
import json
import pathlib
import sys
import time
from unittest.mock import patch

import pytest

# Make conftest importable
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from conftest import FakeTokenizer


@pytest.mark.skipif(not hasattr(__import__("pty"), "fork"), reason="pty module required")
def test_e2e_handoff_restart_real_pty(tmp_path):
    """E2E: real PTY handoff→restart cycle with state transitions and injection.

    1. Spawn a dummy child process via pty.fork()
    2. Set session_type = "orchestrator" (so handoff writes directly, no /handoff\r)
    3. Trigger handoff -> write handoff_complete.json -> child processes it
    4. Assert state: IDLE → HANDOFF_PENDING → RESTARTING → IDLE
    5. Assert child_pid changed (new child spawned)
    6. Assert on_enter_idle injected /orchestrate\r into PTY inputs
    """
    import pty
    import os
    import signal
    from agentflow.shell.session_manager import SessionManager
    from agentflow.shell.state_machine import States

    # Setup: create a short-lived child that produces output repeatedly
    child_cmd = [
        sys.executable,
        "-c",
        "import time,sys; [print('x',flush=True) or time.sleep(0.05) for _ in range(200)]",
    ]

    # Fork PTY manually for real shell execution
    child_pid, master_fd = pty.fork()

    if child_pid == 0:
        # Child process: exec command
        os.environ["AGENTFLOW_PTY"] = "1"
        try:
            os.execvp(child_cmd[0], child_cmd)
        except Exception:
            os._exit(127)

    # Parent: wrap child_pid/master_fd in a real PTY wrapper
    import fcntl
    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    # Create a minimal PTY wrapper-like object
    class RealPTYWrapper:
        def __init__(self, cmd, child_pid, master_fd):
            self._command = cmd
            self.child_pid = child_pid
            self.master_fd = master_fd
            self._exited = False
            self._exit_code = None
            self._on_output = None
            self._on_exit = None
            self.inputs = []

        def write_input(self, text: str) -> None:
            self.inputs.append(text)
            try:
                os.write(self.master_fd, text.encode("utf-8"))
            except OSError:
                pass

        def read_output(self, timeout: float = 0.1) -> bytes:
            import select
            try:
                ready, _, _ = select.select([self.master_fd], [], [], timeout)
                if ready:
                    return os.read(self.master_fd, 1024)
            except (OSError, ValueError):
                self._exited = True
                self._exit_code = -1
                if self._on_exit:
                    self._on_exit(-1)
                    self._on_exit = None
            return b""

    pty_wrapper = RealPTYWrapper(child_cmd, child_pid, master_fd)
    tokenizer = FakeTokenizer()

    # Setup paths
    (tmp_path / ".agentflow").mkdir(parents=True, exist_ok=True)

    # Create SessionManager with real PTY
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        sm = SessionManager(pty_wrapper, tokenizer, {})
        sm._project_root = tmp_path
        sm.session_type = "orchestrator"

        # Initial state check
        assert sm._state_machine.state == States.IDLE
        original_child_pid = pty_wrapper.child_pid

        # Trigger handoff
        sm.trigger_handoff("test")
        assert sm._state_machine.state == States.HANDOFF_PENDING

        # Check that the session-namespaced handoff_complete file was written (orchestrator writes directly)
        handoff_path = sm._handoff_complete_path
        # For orchestrator, the file is written during on_enter_handoff_pending, synchronously
        time.sleep(0.1)  # brief pause to ensure file is written
        assert handoff_path.exists(), "handoff_complete file must be written by on_enter_handoff_pending"

        # Poll for state transition: HANDOFF_PENDING → RESTARTING → IDLE
        # Note: on_enter_restarting runs synchronously and quickly transitions to IDLE
        deadline = time.monotonic() + 3.0
        while sm._state_machine.state != States.IDLE and time.monotonic() < deadline:
            time.sleep(0.05)
            sm.poll()

        assert sm._state_machine.state == States.IDLE, (
            f"Expected final state IDLE, got {sm._state_machine.state}"
        )

        # Verify child_pid changed (new child spawned)
        new_child_pid = pty_wrapper.child_pid
        assert new_child_pid != original_child_pid, "child_pid must change after restart"

        # T-195: skill is now a spawn positional arg, not a PTY stdin injection.
        # Verify _just_restarted was consumed (cleared by on_enter_idle) and no injection in pty inputs.
        assert sm._just_restarted is False, "_just_restarted must be cleared after reaching IDLE"
        orchestrate_inputs = [s for s in pty_wrapper.inputs if "/orchestrate" in s]
        assert orchestrate_inputs == [], (
            f"T-195: /orchestrate must not be written to PTY stdin; got {pty_wrapper.inputs}"
        )

    # Cleanup: kill child
    try:
        os.kill(new_child_pid, signal.SIGTERM)
        time.sleep(0.1)
        try:
            os.waitpid(new_child_pid, os.WNOHANG)
        except ChildProcessError:
            pass
    except OSError:
        pass

    try:
        os.close(master_fd)
    except OSError:
        pass
