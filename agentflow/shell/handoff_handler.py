"""Handoff logic extracted from session_manager."""
from __future__ import annotations
import os
import time
from agentflow.shell.state_machine import States

def handle_enter_handoff_pending(manager) -> None:
    try:
        manager._pty.write_input("/handoff\n")
    except OSError:
        manager._log_audit({"event": "handoff_aborted", "trigger": manager._current_trigger, "tokens": manager._last_accumulated_tokens})
        manager._state_machine.transition("handoff_aborted")
        raise

def run_handoff_loop(manager, trigger: str) -> None:
    deadline = time.monotonic() + 120.0
    while time.monotonic() < deadline:
        if getattr(manager._pty, "_exited", False):
            manager._log_audit({"event": "handoff_aborted", "trigger": trigger, "tokens": manager._last_accumulated_tokens})
            manager._state_machine.transition("pty_eof")
            return

        if manager._handoff_complete_path.exists():
            manager._state_machine.transition("handoff_complete_written")
            return

        try:
            chunk = manager._pty.read_output(timeout=0.01)
            if chunk:
                try:
                    os.write(1, chunk)
                except OSError:
                    pass
                text = chunk.decode("utf-8", errors="replace")
                if "HANDOFF_COMPLETE" in text:
                    manager._handoff_complete_path.parent.mkdir(parents=True, exist_ok=True)
                    manager._handoff_complete_path.write_text("{}", encoding="utf-8")
                    manager._state_machine.transition("handoff_complete_written")
                    return
        except OSError:
            manager._log_audit({"event": "handoff_aborted", "trigger": trigger, "tokens": manager._last_accumulated_tokens})
            manager._state_machine.transition("handoff_aborted")
            return

        time.sleep(0.01)

    manager._log_audit({"event": "handoff_aborted", "trigger": trigger, "tokens": manager._last_accumulated_tokens})
    manager._state_machine.transition("handoff_aborted")

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

    if manager._state_machine.state != States.HANDOFF_PENDING:
        return

    in_pytest = "PYTEST_CURRENT_TEST" in os.environ
    run_sync_loop = in_pytest and not getattr(manager, "_force_async_handoff", False)
    
    if run_sync_loop:
        run_handoff_loop(manager, trigger)

def poll_session(manager) -> None:
    # Any state -> DEAD_CHILD on PTY master fd EOF or process exit
    if getattr(manager._pty, "_exited", False):
        manager._state_machine.transition("pty_eof")
        return

    state = manager._state_machine.state

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

    elif state == States.TASK_COMPLETE:
        manager._state_machine.transition("check_tokens", tokens=manager._last_accumulated_tokens)

    elif state == States.HANDOFF_PENDING:
        if manager._handoff_complete_path.exists():
            manager._state_machine.transition("handoff_complete_written")
