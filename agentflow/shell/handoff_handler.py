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
    # Clear any stale handoff_complete so the poll loop cannot
    # immediately re-trigger a restart from a previous session's file.
    stale = manager._handoff_complete_path
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
    """Non-blocking waitpid loop — avoids hanging if SIGKILL is delayed."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            p, _ = os.waitpid(pid, os.WNOHANG)
            if p == pid:
                return
        except ChildProcessError:
            return
        except OSError:
            return
        time.sleep(0.05)


def _kill_child(manager) -> None:
    """SIGKILL child process; swallow all OS errors."""
    pid = getattr(manager._pty, "child_pid", None)
    manager._log_audit({"event": "kill_child", "pid": pid, "signal": "SIGKILL", "caller": "deadline_expired"})
    if pid:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        _reap_child(pid)


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
        if manager.session_type == "orchestrator" and manager._current_round_path.exists():
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


def check_drain_restart(manager) -> None:
    """Trigger restart when tasks_in_flight drains to empty and context fill >= 80K.

    All conditions must be true:
    1. session_type == "orchestrator"
    2. state is IDLE or TASK_RUNNING (not HANDOFF_PENDING/RESTARTING)
    3. handoff not in progress and not disabled
    4. tasks_in_flight.json absent or empty
    5. current_round.json exists (prevents spurious startup trigger)
    6. context_fill.json fill_tokens >= handoff_primary_tokens
    """
    import json as _json
    def _skip(reason: str, **extra) -> None:
        key = f"_skip_last_{reason}"
        now = time.monotonic()
        if now - getattr(manager, key, 0.0) < 30.0:
            return
        setattr(manager, key, now)
        manager._log_audit({"event": "drain_check_skip", "reason": reason, **extra})

    if manager.session_type != "orchestrator":
        return
    cooldown_remaining = 30.0 - (time.monotonic() - getattr(manager, "_last_restart_ts", 0.0))
    if cooldown_remaining > 0:
        _skip("cooldown", cooldown_remaining=round(cooldown_remaining, 1))
        return
    state = manager._state_machine.state
    if state not in (States.IDLE, States.TASK_RUNNING):
        _skip("state_not_idle", state=str(state))
        return
    if manager._handoff_in_progress or manager._auto_handoff_disabled():
        _skip("handoff_in_progress_or_disabled", in_progress=manager._handoff_in_progress)
        return
    if not manager._current_round_path.exists():
        _skip("no_current_round")
        return
    tif = manager._project_root / ".agentflow" / "tasks_in_flight.json"
    if not tif.exists():
        # absent = round not initialized; [] tombstone = drained; non-empty = tasks running
        _skip("no_tasks_in_flight_file")
        return
    try:
        tif_content = _json.loads(tif.read_text("utf-8"))
        if tif_content:
            _skip("tasks_in_flight_nonempty", tasks=tif_content)
            return
    except Exception as e:
        _skip("tif_read_error", error=str(e))
        return
    threshold = manager._config.get("handoff_primary_tokens", 80000)
    fill_tokens = 0
    try:
        cf = manager._project_root / ".agentflow" / "context_fill.json"
        if cf.exists():
            fill_tokens = _json.loads(cf.read_text("utf-8")).get("fill_tokens", 0)
    except Exception:
        pass
    if fill_tokens < threshold:
        _skip("fill_tokens_below_threshold", fill_tokens=fill_tokens, threshold=threshold)
        return
    manager._log_audit({"event": "drain_restart_triggered", "fill_tokens": fill_tokens, "threshold": threshold})
    # T-209: bypass HANDOFF_PENDING for orchestrate — transition directly to RESTARTING
    manager._state_machine.transition("restart_session")
