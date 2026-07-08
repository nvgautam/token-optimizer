"""Core tests for agentflow.shell.session_manager and agentflow.shell.countdown."""
from __future__ import annotations
import json
import pathlib
import sys
from unittest.mock import MagicMock, patch
import pytest
from agentflow.shell.session_manager import SessionManager
from agentflow.shell.state_machine import States
from agentflow.shell.countdown import countdown

# Make conftest importable
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from conftest import make_manager, fire_output, FakePTY, FakeTokenizer

def test_session_types():
    sm, pty, _ = make_manager()
    fire_output(sm, pty, "/oracle\r\n")
    assert sm.session_type == "oracle"
    sm2, pty2, _ = make_manager()
    fire_output(sm2, pty2, "/orchestrate\r\n")
    assert sm2.session_type == "orchestrator"


def test_countdown_behavior(capsys):
    callback = MagicMock()
    with patch("agentflow.shell.countdown.time") as mock_time:
        mock_time.sleep = MagicMock()
        countdown(3, on_complete=callback)
    callback.assert_called_once()
    assert "Restarting" in capsys.readouterr().err
    callback.reset_mock()
    with patch("agentflow.shell.countdown.time") as mock_time:
        mock_time.sleep = MagicMock(side_effect=KeyboardInterrupt)
        countdown(3, on_complete=callback)
    callback.assert_not_called()


def test_turn_output_history():
    # Turn boundary is triggered by AGENTFLOW_TASK_COMPLETE, not double-newline
    sm, pty, _ = make_manager()
    for _ in range(3):
        fire_output(sm, pty, "response")
    pre_boundary = sm._current_turn_output_tokens
    assert pre_boundary > 1
    # Double-newline should NOT trigger a boundary (old heuristic removed)
    fire_output(sm, pty, "\n\n")
    assert sm._turn_output_history == []
    assert sm._current_turn_output_tokens >= pre_boundary
    # AGENTFLOW_TASK_COMPLETE triggers the boundary
    sm2, pty2, _ = make_manager()
    for _ in range(3):
        fire_output(sm2, pty2, "response")
    pre2 = sm2._current_turn_output_tokens
    fire_output(sm2, pty2, "AGENTFLOW_TASK_COMPLETE:T-001\n")
    assert len(sm2._turn_output_history) == 1
    assert sm2._turn_output_history[0] >= pre2
    assert sm2._current_turn_output_tokens == 0
    # History trimmed to 10 items
    sm3, pty3, _ = make_manager()
    for i in range(15):
        fire_output(sm3, pty3, "response")
        fire_output(sm3, pty3, f"AGENTFLOW_TASK_COMPLETE:T-{i:03d}\n")
    assert len(sm3._turn_output_history) == 10


def test_incremental_write_verbosity_log(tmp_path):
    # Turn boundary (and verbosity log write) is triggered by AGENTFLOW_TASK_COMPLETE signal
    # Without .agentflow dir, no log is written
    sm, pty, _ = make_manager()
    fire_output(sm, pty, "some response")
    fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-001\n")
    assert not (tmp_path / ".agentflow" / "verbosity_log.jsonl").exists()
    # With .agentflow dir, log is written on task complete
    (tmp_path / ".agentflow").mkdir(exist_ok=True)
    sm2, pty2, _ = make_manager()
    sm2.session_type = "oracle"
    fire_output(sm2, pty2, "some response")
    fire_output(sm2, pty2, "AGENTFLOW_TASK_COMPLETE:T-001\n")
    log_path = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1 and json.loads(lines[0])["turn"] == 1


def test_on_session_exit_registered_on_pty():
    sm, pty, _ = make_manager()
    assert pty._on_exit == sm._on_session_exit


def test_ansi_strip():
    sm, _, _ = make_manager()
    assert sm._ansi_strip("\x1b[32mGreen text\x1b[0m") == "Green text"


def test_detect_read_path():
    sm, _, _ = make_manager()
    assert sm._detect_read_path("Read tool agentflow/config/settings.py") == "agentflow/config/settings.py"


def test_init_state_with_preexisting_current_round(tmp_path):
    (tmp_path / ".agentflow").mkdir()
    (tmp_path / ".agentflow" / "current_round.json").write_text("{}", encoding="utf-8")
    pty, tok = FakePTY(), FakeTokenizer()
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm = SessionManager(pty, tok, {})
    assert sm._state_machine.state == States.TASK_RUNNING
    (tmp_path / ".agentflow" / "task_complete.json").write_text("{}", encoding="utf-8")
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm2 = SessionManager(pty, tok, {})
    assert sm2._state_machine.state == States.IDLE


def test_on_enter_idle_reinjects_skill():
    """Test that on_enter_idle reinjects the correct skill based on session_type."""
    from unittest.mock import MagicMock

    # Test orchestrator case
    sm, pty, _ = make_manager()
    sm._just_restarted = True
    sm.session_type = "orchestrator"
    sm.on_enter_idle()
    assert "/orchestrate\r" in pty.inputs
    assert sm._just_restarted is False

    # Test oracle case
    sm2, pty2, _ = make_manager()
    sm2._just_restarted = True
    sm2.session_type = "oracle"
    sm2.on_enter_idle()
    assert "/oracle\r" in pty2.inputs
    assert sm2._just_restarted is False

    # Test None case (no injection)
    sm3, pty3, _ = make_manager()
    sm3._just_restarted = True
    sm3.session_type = None
    sm3.on_enter_idle()
    assert len(pty3.inputs) == 0
    assert sm3._just_restarted is False


def test_restart_end_to_end_via_state_machine():
    """Test the full restart flow: _just_restarted → on_enter_idle → skill reinjection."""
    sm, pty, _ = make_manager()
    sm.session_type = "orchestrator"
    sm._just_restarted = True

    # Simulate transitioning to idle state which calls on_enter_idle
    sm.on_enter_idle()

    # Verify skill was reinjected
    assert "/orchestrate\r" in pty.inputs

    # Verify _just_restarted flag was cleared
    assert sm._just_restarted is False


def test_on_enter_idle_oserror_safe():
    """Test that OSError during skill injection is caught and does not propagate."""
    from unittest.mock import MagicMock

    sm, pty, _ = make_manager()
    sm.session_type = "orchestrator"
    sm._just_restarted = True

    # Mock write_input to raise OSError
    pty.write_input = MagicMock(side_effect=OSError("Broken pipe"))

    # Should not raise an exception
    sm.on_enter_idle()

    # Verify _just_restarted was still cleared despite the error
    assert sm._just_restarted is False

    # Verify write_input was attempted
    pty.write_input.assert_called_once_with("/orchestrate\r")
