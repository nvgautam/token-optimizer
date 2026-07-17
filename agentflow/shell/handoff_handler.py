"""Handoff logic extracted from session_manager."""
from __future__ import annotations
import json
import os
import signal
import time
from agentflow.shell.state_machine import States
from agentflow.shell.drain_restart import _write_merged_and_clear, check_drain_restart

_DEADLINES: dict[States, float] = {
    States.TASK_COMPLETE: 30.0,
    States.HANDOFF_PENDING: 90.0,
    States.RESTARTING: 30.0,
    States.DEAD_CHILD: 10.0,
}


def handle_enter_handoff_pending(manager) -> None:
    stale = manager._handoff_complete_path
    if stale.exists():
        stale.unlink()
        manager._log_audit({"event": "handoff_complete_unlinked"})
    if manager.session_type == "orchestrator":
        hc_path = manager._handoff_complete_path
        try:
            hc_path.parent.mkdir(parents=True, exist_ok=True)
            hc_path.write_text(json.dumps({"status": "complete", "source": "direct"}), encoding="utf-8")
            manager._log_audit({"event": "handoff_complete_written", "source": "direct"})
        except OSError:
            manager._log_audit({"event": "handoff_aborted", "trigger": manager._current_trigger, "tokens": manager._last_accumulated_tokens})
        return
    try:
        manager._pty.write_input("/handoff\r")
    except OSError:
        manager._log_audit({"event": "handoff_aborted", "trigger": manager._current_trigger, "tokens": manager._last_accumulated_tokens})
        manager._state_machine.transition("handoff_aborted")
        raise


def trigger_handoff(manager, trigger: str = "auto") -> None:
    manager._current_trigger = trigger
    if getattr(manager._pty, "_exited", False):
        manager._log_audit({"event": "handoff_aborted", "trigger": trigger, "tokens": manager._last_accumulated_tokens, "session_type": manager.session_type})
        manager._state_machine.transition("pty_eof")
        return
    if not manager._manual_handoff:
        manager._manual_handoff = True
        manager._log_audit({"event": "manual_handoff_set", "source": "trigger_handoff"})
    manager._log_audit({"event": "trigger_handoff", "trigger": trigger, "session_type": manager.session_type, "tokens": manager._last_accumulated_tokens, "state": manager._state_machine.state.value})
    try:
        manager._state_machine.transition("trigger_handoff")
    except OSError:
        return


def _reap_child(pid: int, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            p, _ = os.waitpid(pid, os.WNOHANG)
            if p == pid:
                return
        except (ChildProcessError, OSError):
            return
        time.sleep(0.05)


def _kill_child(manager) -> None:
    pid = getattr(manager._pty, "child_pid", None)
    manager._log_audit({"event": "kill_child", "pid": pid, "signal": "SIGKILL", "caller": "deadline_expired"})
    if pid:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError as e:
            manager._log_audit({"event": "kill_child_error", "error": str(e)})
        _reap_child(pid)


def _check_deadline(manager, state: States) -> bool:
    deadline = _DEADLINES.get(state)
    if deadline is None:
        return False
    now = time.monotonic()
    if getattr(manager, "_deadline_state", None) != state:
        manager._deadline_state = state
        manager._deadline_entered_at = now
        return False
    if now - manager._deadline_entered_at > deadline:
        manager._log_audit({"event": "deadline_expired", "state": state.value})
        _kill_child(manager)
        manager._state_machine.state = States.IDLE
        manager._deadline_state = None
        manager._deadline_entered_at = 0.0
        return True
    return False


def poll_session(manager) -> None:
    state = manager._state_machine.state
    if state == States.HANDOFF_PENDING and manager._handoff_complete_path.exists():
        manager._state_machine.transition("handoff_complete_written")
        return
    if getattr(manager._pty, "_exited", False):
        manager._state_machine.transition("pty_eof")
        return
    if getattr(manager, "_deadline_state", None) != state and state not in _DEADLINES:
        manager._deadline_state = None
        manager._deadline_entered_at = 0.0
    if state == States.IDLE:
        if manager.session_type == "orchestrator" and manager._current_round_path.exists():
            try:
                mtime = manager._current_round_path.stat().st_mtime
                if mtime > manager._last_current_round_mtime:
                    try:
                        data = json.loads(manager._current_round_path.read_text(encoding="utf-8"))
                        file_sid = data.get("session_id")
                        env_sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
                        if not file_sid or file_sid != env_sid:
                            manager._last_current_round_mtime = mtime
                            key = "_skip_last_poll_session_sid_mismatch"
                            now = time.monotonic()
                            if now - getattr(manager, key, 0.0) >= 300.0:
                                setattr(manager, key, now)
                                manager._log_audit({"event": "poll_session_sid_mismatch", "file_sid": file_sid, "env_sid": env_sid})
                            return
                    except Exception as e:
                        manager._log_audit({"event": "poll_session_current_round_read_error", "error": str(e)})
                    manager._state_machine.transition("current_round_written")
            except Exception as e:
                manager._log_audit({"event": "poll_session_stat_error", "error": str(e)})
    elif state == States.TASK_RUNNING:
        if manager._task_complete_path.exists():
            manager._state_machine.transition("task_complete_written")
    elif state == States.TASK_COMPLETE:
        if _check_deadline(manager, state):
            return
        manager._state_machine.transition("task_round_complete")
    elif state == States.HANDOFF_PENDING:
        _check_deadline(manager, state)
    elif state == States.RESTARTING:
        _check_deadline(manager, state)
    elif state == States.DEAD_CHILD:
        _check_deadline(manager, state)
