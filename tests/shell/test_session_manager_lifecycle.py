"""Tests for state machine and lifecycle in agentflow.shell.session_manager."""
from __future__ import annotations
import pathlib
import sys
from unittest.mock import patch
import pytest
from agentflow.shell.state_machine import States

# Make conftest importable
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from conftest import make_manager


def test_on_enter_restarting_calls_restart_child():
    sm, pty, _ = make_manager()
    with patch.object(sm, "restart_child") as mock_restart:
        sm.on_enter_restarting()
        mock_restart.assert_called_once()
        assert sm._just_restarted is True
        assert not any("/clear" in inp for inp in pty.inputs)

def test_restart_child_resets_token_accumulator(tmp_path):
    """T-150: restart_child() must zero _last_accumulated_tokens and reset the tokenizer."""
    sm, pty, tok = make_manager()
    pty.child_pid = None  # no real process to kill

    # Simulate accumulated tokens from a previous session
    sm._last_accumulated_tokens = 95_000
    tok._total = 95_000

    with (
        patch("agentflow.shell.process_manager.spawn_new_child"),
        patch.object(sm._state_machine, "transition"),
    ):
        sm.restart_child()

    assert sm._last_accumulated_tokens == 0, "_last_accumulated_tokens must be reset to 0 after restart"
    assert tok._total == 0, "tokenizer running total must be reset to 0 after restart"

def test_idle_poll_no_longer_triggers_on_token_count(tmp_path):
    """T-151: poll() must NOT trigger handoff based on safety/ceiling token counts.
    The poll loop only responds to signal files; threshold-based triggers are
    exclusively handled in output_handler via the primary path."""
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        # 125K tokens — formerly triggered safety handoff; must stay IDLE now
        sm, pty, _ = make_manager(config={"handoff_primary_tokens": 80_000})
        sm._state_machine.state = States.IDLE
        sm._last_accumulated_tokens = 125_000
        with patch.object(sm, "trigger_handoff") as mock_hf:
            sm.poll()
            mock_hf.assert_not_called()
        assert sm._state_machine.state == States.IDLE

        # 155K tokens — formerly triggered ceiling handoff; must stay IDLE now
        sm2, pty2, _ = make_manager(config={"handoff_primary_tokens": 80_000})
        sm2._state_machine.state = States.IDLE
        sm2._last_accumulated_tokens = 155_000
        with patch.object(sm2, "trigger_handoff") as mock_hf:
            sm2.poll()
            mock_hf.assert_not_called()
        assert sm2._state_machine.state == States.IDLE

def test_init_state_with_preexisting_current_round(tmp_path):
    (tmp_path / ".agentflow").mkdir()
    (tmp_path / ".agentflow" / "current_round.json").write_text("{}", encoding="utf-8")
    from conftest import FakePTY, FakeTokenizer
    from agentflow.shell.session_manager import SessionManager
    pty, tok = FakePTY(), FakeTokenizer()
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm = SessionManager(pty, tok, {})
    assert sm._state_machine.state == States.TASK_RUNNING
    (tmp_path / ".agentflow" / "task_complete.json").write_text("{}", encoding="utf-8")
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm2 = SessionManager(pty, tok, {})
    assert sm2._state_machine.state == States.IDLE

# --- T-121: per-state deadlines, ANSI reset, stdin gating ---
@pytest.mark.parametrize("state,elapsed,expect_idle", [
    (States.HANDOFF_PENDING, 91, True), (States.TASK_COMPLETE, 31, True),
    (States.RESTARTING, 31, True), (States.DEAD_CHILD, 11, True),
    (States.TASK_RUNNING, 1000, False),
])
def test_deadline_fires(tmp_path, state, elapsed, expect_idle):
    sm, _, _ = make_manager()
    sm._state_machine.state = state
    sm._deadline_state = state
    sm._deadline_entered_at = 0.0
    with patch("agentflow.shell.handoff_handler.time") as mt:
        mt.monotonic.return_value = elapsed
        with patch("os.kill"), patch("os.waitpid", return_value=(0, 0)):
            sm.poll()
    assert sm._state_machine.state == (States.IDLE if expect_idle else state)

def test_handoff_complete_via_poll_not_loop(tmp_path):
    sm, _, _ = make_manager()
    sm._state_machine.state = States.HANDOFF_PENDING
    sm._handoff_complete_path = tmp_path / ".agentflow" / "handoff_complete.json"
    sm._handoff_complete_path.parent.mkdir(parents=True, exist_ok=True)
    sm._handoff_complete_path.write_text("{}", encoding="utf-8")
    with patch.object(sm, "restart_child"): sm.poll()
    assert sm._state_machine.state == States.RESTARTING

def test_on_enter_restarting_emits_ansi_reset():
    sm, _, _ = make_manager()
    written = []
    with patch("os.write", side_effect=lambda fd, b: written.append((fd, b))):
        with patch.object(sm, "restart_child"): sm.on_enter_restarting()
    assert (1, b"\x1b[0m") in written

def test_stdin_gating_condition():
    sm, _, _ = make_manager()
    sm._state_machine.state = States.RESTARTING
    assert (sm._state_machine.state != States.RESTARTING) is False
    sm._state_machine.state = States.IDLE
    assert (sm._state_machine.state != States.RESTARTING) is True
