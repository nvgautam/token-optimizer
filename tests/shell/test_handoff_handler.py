"""Tests for handoff_handler.py — T-159 session_type branch."""
from __future__ import annotations

import json
import pathlib
import time
from unittest.mock import MagicMock, patch

import pytest

from agentflow.shell.handoff_handler import (
    _check_deadline,
    handle_enter_handoff_pending,
    poll_session,
    trigger_handoff,
)
from agentflow.shell.state_machine import States


# --------------------------------------------------------------------------- #
# Shared helpers                                                               #
# --------------------------------------------------------------------------- #

def _handoff_manager(tmp_path: pathlib.Path, session_type=None) -> MagicMock:
    """Mock manager for handle_enter_handoff_pending tests."""
    m = MagicMock()
    m.session_type = session_type
    m._current_trigger = "auto"
    m._last_accumulated_tokens = 1234
    m._handoff_complete_path = tmp_path / ".agentflow" / "handoff_complete.json"
    return m


def _poll_manager(state: States, tmp_path: pathlib.Path) -> MagicMock:
    """Mock manager for poll_session / _check_deadline tests."""
    m = MagicMock()
    m._pty._exited = False
    m._state_machine.state = state
    m._deadline_state = None
    m._deadline_entered_at = 0.0
    m._last_accumulated_tokens = 1000
    m._handoff_complete_path = tmp_path / ".agentflow" / "handoff_complete.json"
    m._current_round_path = tmp_path / ".agentflow" / "current_round.json"
    m._task_complete_path = tmp_path / ".agentflow" / "task_complete"
    m._last_current_round_mtime = 0.0
    return m


# --------------------------------------------------------------------------- #
# handle_enter_handoff_pending                                                 #
# --------------------------------------------------------------------------- #

class TestHandleEnterHandoffPending:

    @pytest.mark.parametrize("session_type", ["oracle", None])
    def test_oracle_and_none_inject_handoff(self, tmp_path, monkeypatch, session_type):
        """oracle / None → write_input("/handoff\\r"), no file created."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".agentflow").mkdir()
        m = _handoff_manager(tmp_path, session_type=session_type)

        handle_enter_handoff_pending(m)

        m._pty.write_input.assert_called_once_with("/handoff\r")
        assert not (tmp_path / ".agentflow" / "handoff_complete.json").exists()

    def test_oracle_ioerror_transitions_aborted(self, tmp_path, monkeypatch):
        """oracle write_input OSError → log handoff_aborted + transition + re-raise."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".agentflow").mkdir()
        m = _handoff_manager(tmp_path, session_type="oracle")
        m._pty.write_input.side_effect = OSError("PTY gone")

        with pytest.raises(OSError, match="PTY gone"):
            handle_enter_handoff_pending(m)

        m._log_audit.assert_called_once_with(
            {"event": "handoff_aborted", "trigger": "auto", "tokens": 1234}
        )
        m._state_machine.transition.assert_called_once_with("handoff_aborted")

    def test_orchestrator_path_writes_completion(self, tmp_path, monkeypatch):
        """orchestrator → handoff_complete.json written with correct content."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".agentflow").mkdir()
        m = _handoff_manager(tmp_path, session_type="orchestrator")

        handle_enter_handoff_pending(m)

        cf = tmp_path / ".agentflow" / "handoff_complete.json"
        assert cf.exists()
        assert json.loads(cf.read_text()) == {"status": "complete"}
        m._pty.write_input.assert_not_called()

    def test_orchestrator_path_logs_event(self, tmp_path, monkeypatch):
        """orchestrator → _log_audit called with event='orchestrate_handoff_direct'."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".agentflow").mkdir()
        m = _handoff_manager(tmp_path, session_type="orchestrator")

        handle_enter_handoff_pending(m)

        m._log_audit.assert_called_once()
        assert m._log_audit.call_args[0][0]["event"] == "orchestrate_handoff_direct"

    def test_orchestrator_ioerror_transitions_aborted(self, tmp_path, monkeypatch):
        """orchestrator OSError on write → log handoff_aborted + transition + re-raise."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".agentflow").mkdir()
        m = _handoff_manager(tmp_path, session_type="orchestrator")

        def _raise_oserror(self, *args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(pathlib.Path, "write_text", _raise_oserror)

        with pytest.raises(OSError, match="disk full"):
            handle_enter_handoff_pending(m)

        m._log_audit.assert_called_once_with(
            {"event": "handoff_aborted", "trigger": "auto", "tokens": 1234}
        )
        m._state_machine.transition.assert_called_once_with("handoff_aborted")

    def test_stale_handoff_complete_cleared_oracle(self, tmp_path, monkeypatch):
        """Pre-existing handoff_complete.json removed before oracle path proceeds."""
        monkeypatch.chdir(tmp_path)
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        stale = agentflow_dir / "handoff_complete.json"
        stale.write_text('{"status": "complete"}')

        m = _handoff_manager(tmp_path, session_type="oracle")
        handle_enter_handoff_pending(m)

        assert not stale.exists()
        m._pty.write_input.assert_called_once_with("/handoff\r")

    def test_stale_handoff_complete_cleared_orchestrator(self, tmp_path, monkeypatch):
        """Pre-existing handoff_complete.json removed; orchestrator writes a fresh one."""
        monkeypatch.chdir(tmp_path)
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        stale = agentflow_dir / "handoff_complete.json"
        stale.write_text('{"status": "stale"}')

        m = _handoff_manager(tmp_path, session_type="orchestrator")
        handle_enter_handoff_pending(m)

        cf = tmp_path / ".agentflow" / "handoff_complete.json"
        assert json.loads(cf.read_text()) == {"status": "complete"}


# --------------------------------------------------------------------------- #
# trigger_handoff                                                              #
# --------------------------------------------------------------------------- #

class TestTriggerHandoff:

    def _mgr(self) -> MagicMock:
        m = MagicMock()
        m._last_accumulated_tokens = 500
        m._pty._exited = False
        return m

    def test_normal_logs_and_transitions(self):
        """Normal path: logs trigger_handoff and calls transition."""
        m = self._mgr()
        trigger_handoff(m, trigger="manual")

        assert m._current_trigger == "manual"
        logged = m._log_audit.call_args[0][0]
        assert logged["event"] == "trigger_handoff"
        m._state_machine.transition.assert_called_once_with("trigger_handoff")

    def test_pty_exited_aborts(self):
        """PTY exited → log handoff_aborted + transition(pty_eof)."""
        m = self._mgr()
        m._pty._exited = True

        trigger_handoff(m, trigger="auto")

        logged = m._log_audit.call_args[0][0]
        assert logged["event"] == "handoff_aborted"
        m._state_machine.transition.assert_called_once_with("pty_eof")

    def test_oserror_from_transition_swallowed(self):
        """OSError from transition is swallowed — returns normally."""
        m = self._mgr()
        m._state_machine.transition.side_effect = OSError("busy")

        trigger_handoff(m, trigger="auto")  # must not raise

        m._state_machine.transition.assert_called_once_with("trigger_handoff")


# --------------------------------------------------------------------------- #
# _check_deadline                                                              #
# --------------------------------------------------------------------------- #

class TestCheckDeadline:

    def _mgr(self) -> MagicMock:
        m = MagicMock()
        m._pty.child_pid = None
        return m

    def test_state_not_in_deadlines(self):
        """States.IDLE not in _DEADLINES → returns False immediately."""
        assert _check_deadline(self._mgr(), States.IDLE) is False

    def test_first_entry_records_state(self):
        """First call records deadline_state/entered_at and returns False."""
        m = self._mgr()
        m._deadline_state = None

        result = _check_deadline(m, States.TASK_COMPLETE)

        assert result is False
        assert m._deadline_state == States.TASK_COMPLETE

    def test_deadline_expired_kills_child_and_resets(self):
        """Expired deadline → kills child, resets to IDLE, returns True."""
        m = self._mgr()
        m._deadline_state = States.TASK_COMPLETE
        m._deadline_entered_at = 0.0
        m._pty.child_pid = 99999

        with patch("os.kill"), patch("os.waitpid"):
            result = _check_deadline(m, States.TASK_COMPLETE)

        assert result is True
        logged = m._log_audit.call_args[0][0]
        assert logged["event"] == "deadline_expired"
        assert m._state_machine.state == States.IDLE

    def test_kill_child_oserror_swallowed(self):
        """OSError from os.kill is swallowed; deadline still returns True."""
        m = self._mgr()
        m._deadline_state = States.HANDOFF_PENDING
        m._deadline_entered_at = 0.0
        m._pty.child_pid = 99999

        with patch("os.kill", side_effect=OSError("no such process")):
            assert _check_deadline(m, States.HANDOFF_PENDING) is True


# --------------------------------------------------------------------------- #
# poll_session                                                                 #
# --------------------------------------------------------------------------- #

class TestPollSession:

    def test_pty_exited_transitions_pty_eof(self, tmp_path):
        """PTY exited → transition(pty_eof)."""
        m = _poll_manager(States.IDLE, tmp_path)
        m._pty._exited = True
        poll_session(m)
        m._state_machine.transition.assert_called_once_with("pty_eof")

    def test_idle_round_file_updated(self, tmp_path):
        """IDLE, round file newer than last mtime → transition(current_round_written)."""
        m = _poll_manager(States.IDLE, tmp_path)
        rf = tmp_path / ".agentflow" / "current_round.json"
        (tmp_path / ".agentflow").mkdir(parents=True, exist_ok=True)
        rf.write_text("{}")
        m._current_round_path = rf

        poll_session(m)
        m._state_machine.transition.assert_called_once_with("current_round_written")

    def test_task_running_complete_path_exists(self, tmp_path):
        """TASK_RUNNING, task_complete_path exists → transition(task_complete_written)."""
        m = _poll_manager(States.TASK_RUNNING, tmp_path)
        tc = tmp_path / ".agentflow" / "task_complete"
        (tmp_path / ".agentflow").mkdir(parents=True, exist_ok=True)
        tc.touch()
        m._task_complete_path = tc

        poll_session(m)
        m._state_machine.transition.assert_called_once_with("task_complete_written")

    def test_task_complete_check_tokens(self, tmp_path):
        """TASK_COMPLETE, deadline not expired → transition(check_tokens)."""
        m = _poll_manager(States.TASK_COMPLETE, tmp_path)
        poll_session(m)
        m._state_machine.transition.assert_called_once_with("check_tokens", tokens=1000)

    def test_handoff_pending_file_written(self, tmp_path):
        """HANDOFF_PENDING, file present, no deadline → transition(handoff_complete_written)."""
        m = _poll_manager(States.HANDOFF_PENDING, tmp_path)
        hc = tmp_path / ".agentflow" / "handoff_complete.json"
        (tmp_path / ".agentflow").mkdir(parents=True, exist_ok=True)
        hc.write_text('{"status": "complete"}')
        m._handoff_complete_path = hc

        poll_session(m)
        m._state_machine.transition.assert_called_with("handoff_complete_written")

    @pytest.mark.parametrize("state", [States.RESTARTING, States.DEAD_CHILD])
    def test_restarting_and_dead_child_exercise_deadline(self, tmp_path, state):
        """RESTARTING / DEAD_CHILD → _check_deadline exercised, no transition."""
        m = _poll_manager(state, tmp_path)
        poll_session(m)
        m._state_machine.transition.assert_not_called()
