"""Handler functions and utilities for SessionManager.

These are extracted from session_manager.py to reduce file size
while maintaining all functionality.
"""
from __future__ import annotations
import pathlib


def log_audit(session_manager, entry: dict) -> None:
    """Log an audit event to session audit."""
    from agentflow.shell.session_audit import log_audit as _log_audit
    _log_audit(session_manager, entry)


def apply_session_threshold(session_manager) -> None:
    """Apply configured session threshold."""
    from agentflow.shell.threshold_sync import apply_session_threshold as _apply
    _apply(session_manager)


def sync_session_type(session_manager) -> None:
    """Sync session type from configuration."""
    from agentflow.shell.threshold_sync import sync_session_type as _sync
    _sync(session_manager)


def run_stale_index_guard(session_manager) -> None:
    """Run the stale index guard."""
    from agentflow.shell.stale_index_guard import run_stale_index_guard as _guard
    _guard()


def poll_session(session_manager) -> None:
    """Poll session state from file system."""
    from agentflow.shell.handoff_handler import poll_session as _poll
    _poll(session_manager)


def update_last_current_round_mtime(session_manager) -> None:
    """Update the last known modification time of current_round.json."""
    try:
        mtime = session_manager._current_round_path.stat().st_mtime if session_manager._current_round_path.exists() else 0.0
        session_manager._last_current_round_mtime = mtime
    except Exception as e:
        log_audit(session_manager, {"event": "mtime_stat_error", "error": str(e)})
        session_manager._last_current_round_mtime = 0.0


def clear_signal_files(session_manager) -> None:
    """Clear task completion and handoff signal files."""
    import os
    from agentflow.shell.session_paths import session_file

    for path in [session_manager._task_complete_path, session_manager._handoff_complete_path]:
        try:
            if path.exists():
                path.unlink()
        except Exception as e:
            log_audit(session_manager, {"event": "clear_signal_unlink_error", "error": str(e)})

    # T-219: Use SID-scoped path for context_fill.json reset
    sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
    agentflow_dir = session_manager._project_root / ".agentflow"
    cf = session_file(agentflow_dir, "context_fill.json", sid)
    try:
        cf.write_text('{"fill_tokens": 0}', encoding="utf-8")
    except Exception as e:
        log_audit(session_manager, {"event": "context_fill_reset_error", "error": str(e)})


def handle_enter_handoff_pending(session_manager) -> None:
    """Handle state transition to HANDOFF_PENDING."""
    try:
        import json as _json
        from agentflow.shadow.capacity_calibrator import calibrate_capacity
        current_start_pct = 0.0
        ledger_path = session_manager._project_root / "agentflow_ledger.json"
        if ledger_path.exists():
            try:
                with open(ledger_path, "r") as _f:
                    _ledger = _json.load(_f)
                for _snap in reversed(_ledger.get("usage_snapshots", [])):
                    if _snap.get("label") == "session_start":
                        current_start_pct = float(_snap.get("start_pct_5hr", 0.0))
                        break
            except Exception as e:
                log_audit(session_manager, {"event": "ledger_read_error", "error": str(e)})
        calibrate_capacity(session_manager._project_root, current_start_pct)
    except Exception as e:
        log_audit(session_manager, {"event": "calibrate_capacity_error", "error": str(e)})
    from agentflow.shell.handoff_handler import handle_enter_handoff_pending as _handler
    _handler(session_manager)


def handle_enter_restarting(session_manager) -> None:
    """Handle state transition to RESTARTING."""
    from agentflow.shell.process_manager import handle_enter_restarting as _handler
    _handler(session_manager)


def handle_enter_idle(session_manager) -> None:
    """Handle state transition to IDLE."""
    update_last_current_round_mtime(session_manager)
    clear_signal_files(session_manager)
    session_manager._just_restarted = False


def handle_enter_dead_child(session_manager) -> None:
    """Handle state transition to DEAD_CHILD."""
    log_audit(session_manager, {"event": "dead_child_detected"})


def restart_child_impl(session_manager) -> None:
    """Implementation of restart_child."""
    from agentflow.shell.process_manager import restart_child as _restart
    _restart(session_manager)


def spawn_new_child_impl(session_manager) -> None:
    """Implementation of _spawn_new_child."""
    from agentflow.shell.process_manager import spawn_new_child as _spawn
    _spawn(session_manager)


def handle_output_impl(session_manager, chunk: bytes) -> None:
    """Implementation of _handle_output."""
    from agentflow.shell.output_handler import handle_output as _handle
    _handle(session_manager, chunk)


def record_task_tokens_impl(session_manager, task_id: str, delta: int) -> None:
    """Implementation of _record_task_tokens."""
    from agentflow.shell.output_handler import record_task_tokens as _record
    _record(session_manager, task_id, delta)


def ansi_strip_impl(session_manager, text: str) -> str:
    """Implementation of _ansi_strip."""
    from agentflow.shell.output_handler import ansi_strip as _strip
    return _strip(text)


def detect_read_path_impl(session_manager, text: str) -> str | None:
    """Implementation of _detect_read_path."""
    from agentflow.shell.output_handler import detect_read_path as _detect
    return _detect(text)


def handle_session_exit(session_manager, exit_code: int) -> None:
    """Handle PTY child process exit."""
    from agentflow.shell.state_machine import States

    pid = getattr(session_manager._pty, "child_pid", None)
    log_audit(session_manager, {"event": "session_exit", "exit_code": exit_code, "pid": pid})

    # Oracle auto-restart is DEFERRED — only orchestrator sessions restart on handoff.
    if (session_manager._state_machine.state == States.HANDOFF_PENDING
            and session_manager._handoff_complete_path.exists()
            and getattr(session_manager, "session_type", None) == "orchestrator"):
        session_manager._state_machine.transition("handoff_complete_written")
        return

    # Child exit was expected — restart_child killed it intentionally.
    # Transitioning to DEAD_CHILD here races with restart_done in the same
    # call chain; let restart_child complete the RESTARTING → IDLE arc.
    if session_manager._state_machine.state == States.RESTARTING:
        log_audit(session_manager, {"event": "session_exit_ignored", "reason": "restarting", "exit_code": exit_code, "pid": pid})
        return

    try:
        session_manager._state_machine.transition("pty_eof")
    except Exception as e:
        log_audit(session_manager, {"event": "session_exit_transition_error", "error": str(e)})


def trigger_handoff_impl(session_manager, trigger: str = "auto") -> None:
    """Implementation of trigger_handoff."""
    from agentflow.shell.handoff_handler import trigger_handoff as _trigger
    _trigger(session_manager, trigger)


def restart_session_impl(session_manager) -> None:
    """Implementation of _restart_session."""
    session_manager._state_machine.transition("restart_session")


def update_session_file_impl(session_manager) -> None:
    """Implementation of _update_session_file."""
    from agentflow.shell.session_audit import update_session_file as _update
    _update(session_manager)


def check_drain_restart_impl(session_manager) -> None:
    """Implementation of _check_drain_restart."""
    from agentflow.shell.handoff_handler import check_drain_restart as _check
    _check(session_manager)


def check_debug_restart_trigger_impl(session_manager) -> None:
    """Implementation of _check_debug_restart_trigger."""
    from agentflow.shell.debug_trigger import check_debug_restart_trigger as _check
    _check(session_manager)
