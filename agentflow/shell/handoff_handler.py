"""Handoff logic extracted from session_manager."""
from __future__ import annotations
import json
import os
import pathlib
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
    # Clear any stale handoff_complete.json so the poll loop cannot
    # immediately re-trigger a restart from a previous session's file.
    stale = pathlib.Path(".agentflow/handoff_complete.json")
    if stale.exists():
        stale.unlink()
    if manager.session_type == "orchestrator":
        # Orchestrate sessions manage their own context lifecycle — skip the /handoff LLM
        # skill and write handoff_complete.json directly so the poll loop transitions to
        # RESTARTING without burning extra tokens.
        hc_path = manager._handoff_complete_path
        try:
            hc_path.parent.mkdir(parents=True, exist_ok=True)
            hc_path.write_text(json.dumps({"status": "complete", "source": "direct"}), encoding="utf-8")
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
    state = manager._state_machine.state

    # Check handoff completion BEFORE exit — child may exit the instant it
    # writes handoff_complete.json (oracle flow). _on_session_exit handles the
    # primary path; this poll branch is a defensive fallback.
    if state == States.HANDOFF_PENDING and manager._handoff_complete_path.exists():
        manager._state_machine.transition("handoff_complete_written")
        return

    # Any state -> DEAD_CHILD on PTY master fd EOF or process exit
    if getattr(manager._pty, "_exited", False):
        manager._state_machine.transition("pty_eof")
        return

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
        # T-151: safety and ceiling threshold triggers removed from poll loop.
        # Handoff is only triggered via output_handler (primary: 80K + task_just_completed)
        # or explicit /handoff signal — not by polling token counts here.


    elif state == States.TASK_RUNNING:
        if manager._task_complete_path.exists():
            manager._state_machine.transition("task_complete_written")
        # No deadline for TASK_RUNNING — liveness via waitpid(WNOHANG)

    elif state == States.TASK_COMPLETE:
        if _check_deadline(manager, state):
            return
        manager._state_machine.transition("check_tokens", tokens=manager._last_accumulated_tokens)

    elif state == States.HANDOFF_PENDING:
        _check_deadline(manager, state)

    elif state == States.RESTARTING:
        _check_deadline(manager, state)

    elif state == States.DEAD_CHILD:
        _check_deadline(manager, state)
