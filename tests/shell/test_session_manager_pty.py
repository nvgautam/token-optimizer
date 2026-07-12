"""Tests for PTY injection and signal handling (T-148, T-149)."""
from __future__ import annotations
import pathlib
import sys
from unittest.mock import patch
import pytest

# Make conftest importable
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from conftest import make_manager, fire_output


# ---------------------------------------------------------------------------
# T-148: PTY stdin submission — injected commands must use \r not \n
# ---------------------------------------------------------------------------

def test_t148_handoff_injection_uses_cr(tmp_path):
    """T-148: handle_enter_handoff_pending writes /handoff\\r (CR) not LF.

    PTY line discipline submits on CR (0x0D); LF leaves the command buffered.
    """
    sm, pty, _ = make_manager()
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        original_write = pty.write_input

        def mock_write_input(text):
            original_write(text)
            if "/handoff" in text:
                sm._handoff_complete_path.parent.mkdir(parents=True, exist_ok=True)
                sm._handoff_complete_path.write_text("{}", encoding="utf-8")

        pty.write_input = mock_write_input
        with patch("agentflow.shell.session_manager.countdown") as mock_cd:
            mock_cd.side_effect = lambda s, on_complete, **kw: on_complete()
            sm.trigger_handoff()

    # Must end with \r (0x0D), NOT \n (0x0A)
    handoff_inputs = [s for s in pty.inputs if "/handoff" in s]
    assert handoff_inputs, "No /handoff command was written"
    assert all(s.endswith("\r") for s in handoff_inputs), (
        f"Expected /handoff to end with \\r, got: {handoff_inputs!r}"
    )
    assert not any(s.endswith("\n") for s in handoff_inputs), (
        f"Unexpected LF in /handoff injection: {handoff_inputs!r}"
    )


def test_t148_restart_injection_uses_cr(tmp_path):
    """T-195: restart skill is now passed as spawn positional arg, not PTY injection.

    on_enter_idle no longer writes to PTY stdin; spawn_new_child appends /oracle
    as a positional arg so the CLI receives it at startup without stdin tricks.
    """
    import pty as pty_module
    from agentflow.shell.process_manager import spawn_new_child
    sm, pty, _ = make_manager()
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

    assert exec_called and exec_called[0] == ["claude", "/oracle"], (
        f"Expected ['claude', '/oracle'], got {exec_called}"
    )
    # No PTY injection
    assert len(pty.inputs) == 0, f"No PTY input expected; got {pty.inputs!r}"


def test_t148_restart_injection_orchestrate_uses_cr(tmp_path):
    """T-195: orchestrator spawn passes /orchestrate as positional arg (no PTY injection)."""
    import pty as pty_module
    from agentflow.shell.process_manager import spawn_new_child
    sm, pty, _ = make_manager()
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

    assert exec_called and exec_called[0] == ["claude", "/orchestrate"], (
        f"Expected ['claude', '/orchestrate'], got {exec_called}"
    )
    assert len(pty.inputs) == 0, f"No PTY input expected; got {pty.inputs!r}"


def test_t148_no_lf_in_pty_injections(tmp_path):
    """T-148: no write_input call from handoff/restart paths may end with bare LF.

    Regression guard: if any injection uses \\n instead of \\r, PTY command
    submission silently stalls and the session hangs.
    """
    sm, pty, _ = make_manager()
    sm.session_type = "oracle"
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        original_write = pty.write_input

        def mock_write_input(text):
            original_write(text)
            if "/handoff" in text:
                sm._handoff_complete_path.parent.mkdir(parents=True, exist_ok=True)
                sm._handoff_complete_path.write_text("{}", encoding="utf-8")

        pty.write_input = mock_write_input
        with patch("agentflow.shell.session_manager.countdown") as mock_cd:
            mock_cd.side_effect = lambda s, on_complete, **kw: on_complete()
            sm.trigger_handoff()

    # Filter to command-injection inputs only (not user pass-through)
    slash_inputs = [s for s in pty.inputs if s.startswith("/") and s.strip("/") in
                    ("handoff\r", "oracle\r", "orchestrate\r", "handoff\n", "oracle\n", "orchestrate\n")]
    bare_lf = [s for s in slash_inputs if s.endswith("\n") and not s.endswith("\r\n")]
    assert bare_lf == [], (
        f"T-148 regression: these injections use bare LF instead of CR: {bare_lf!r}"
    )


# ---------------------------------------------------------------------------
# T-149: stale handoff_complete.json is cleared before poll loop
# ---------------------------------------------------------------------------

def test_t149_stale_handoff_complete_cleared_on_enter(tmp_path, monkeypatch):
    """T-149: handle_enter_handoff_pending deletes a pre-existing handoff_complete file.

    A stale file from a previous session must be removed *before* write_input
    is called so the poll loop cannot instantly see it and trigger a restart storm.
    """
    from agentflow.shell.handoff_handler import handle_enter_handoff_pending

    monkeypatch.chdir(tmp_path)
    stale_dir = tmp_path / ".agentflow"
    stale_dir.mkdir(parents=True, exist_ok=True)

    # Build manager first so we can resolve the session-namespaced path
    sm, pty, _ = make_manager()
    sm._current_trigger = "auto"
    sm._last_accumulated_tokens = 0

    # Place the stale file at the path the handler will look for
    stale_file = sm._handoff_complete_path
    stale_file.write_text("{}", encoding="utf-8")
    assert stale_file.exists(), "pre-condition: stale file must exist"

    # Track deletion order vs write_input order
    deleted_before_write = []

    original_write = pty.write_input

    def tracking_write(text):
        # At the moment write_input is called, the stale file must already be gone
        deleted_before_write.append(not stale_file.exists())
        original_write(text)

    pty.write_input = tracking_write

    handle_enter_handoff_pending(sm)

    assert not stale_file.exists(), "stale handoff_complete file must be deleted by handle_enter_handoff_pending"
    assert deleted_before_write, "write_input must have been called"
    assert all(deleted_before_write), "stale file must be deleted BEFORE write_input is called"


def test_t149_no_stale_file_is_noop(tmp_path, monkeypatch):
    """T-149: handle_enter_handoff_pending is a no-op when no stale file exists."""
    from agentflow.shell.handoff_handler import handle_enter_handoff_pending

    monkeypatch.chdir(tmp_path)
    stale_file = tmp_path / ".agentflow" / "handoff_complete.json"
    assert not stale_file.exists(), "pre-condition: no stale file"

    sm, pty, _ = make_manager()
    sm._current_trigger = "auto"
    sm._last_accumulated_tokens = 0

    # Should not raise; write_input should still be called normally
    handle_enter_handoff_pending(sm)

    assert not stale_file.exists()
    assert any("/handoff" in s for s in pty.inputs), "write_input('/handoff\\r') must still be called"
