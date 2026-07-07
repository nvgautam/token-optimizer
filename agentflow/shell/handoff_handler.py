"""Handoff logic extracted from session_manager."""
from __future__ import annotations
import os
import signal
import time
from agentflow.shell.state_machine import States

_DEADLINES: dict[States, float] = {
    States.TASK_COMPLETE: 30.0,
    States.HANDOFF_PENDING: 90.0,
    States.RESTARTING: 30.0,
    States.DEAD_CHILD: 10.0,
}


def handle_enter_handoff_pending(manager) -> None:
    try:
        manager._pty.write_input("/handoff\n")
    except OSError:
        manager._log_audit({"event": "handoff_aborted", "trigger": manager._current_trigger, "tokens": manager._last_accumulated_tokens})
        manager._state_machine.transition("handoff_aborted")
        raise


def trigger_handoff(manager, trigger: str = "auto") -> None:
    manager._current_trigger = trigger
    if getattr(manager._pty, "_exited", False):
        manager._log_audit({"event": "handoff_aborted", "trigger": trigger, "tokens": manager._last_accumulated_tokens})
        manager._state_machine.transition("pty_eof")
        return

    manager._log_audit({"event": "trigger_handoff", "trigger": trigger})
    try:
        manager._state_machine.transition("trigger_handoff")
    except OSError:
        return


def _kill_child(manager) -> None:
    """SIGKILL child process; swallow all OS errors."""
    pid = getattr(manager._pty, "child_pid", None)
    if pid:
        try:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        except OSError:
            pass


def _check_deadline(manager, state: States) -> bool:
    """Return True and force IDLE if deadline for *state* has elapsed."""
    deadline = _DEADLINES.get(state)
    if deadline is None:
        return False
    now = time.monotonic()
    # Track when we entered this state
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
    # Any state -> DEAD_CHILD on PTY master fd EOF or process exit
    if getattr(manager._pty, "_exited", False):
        manager._state_machine.transition("pty_eof")
        return

    state = manager._state_machine.state

    # Reset deadline tracking when state changes
    if getattr(manager, "_deadline_state", None) != state and state not in _DEADLINES:
        manager._deadline_state = None
        manager._deadline_entered_at = 0.0

    if state == States.IDLE:
        if manager._current_round_path.exists():
            try:
                mtime = manager._current_round_path.stat().st_mtime
                if mtime > manager._last_current_round_mtime:
                    manager._state_machine.transition("current_round_written")
            except Exception:
                pass
        elif not manager._manual_handoff and not manager._auto_handoff_disabled():
            task_in_flight = bool(manager._task_start_tokens) or manager._state_machine.state == States.TASK_RUNNING
            safety = manager._config.get("handoff_safety_tokens", 120000)
            ceiling = manager._config.get("handoff_hard_ceiling_tokens", 150000)
            if manager._last_accumulated_tokens >= ceiling:
                manager.trigger_handoff(trigger="auto-ceiling")
            elif manager._last_accumulated_tokens >= safety and not task_in_flight:
                manager.trigger_handoff(trigger="auto-safety")

    elif state == States.TASK_RUNNING:
        if manager._task_complete_path.exists():
            manager._state_machine.transition("task_complete_written")
        # No deadline for TASK_RUNNING — liveness via waitpid(WNOHANG)

    elif state == States.TASK_COMPLETE:
        if _check_deadline(manager, state):
            return
        manager._state_machine.transition("check_tokens", tokens=manager._last_accumulated_tokens)

    elif state == States.HANDOFF_PENDING:
        if _check_deadline(manager, state):
            return
        if manager._handoff_complete_path.exists():
            manager._state_machine.transition("handoff_complete_written")

    elif state == States.RESTARTING:
        _check_deadline(manager, state)

    elif state == States.DEAD_CHILD:
        _check_deadline(manager, state)
