"""Handoff logic extracted from session_manager."""
from __future__ import annotations
import fcntl
import json
import os
import re
import signal
import tempfile
import time
from agentflow.shell.state_machine import States
from agentflow.shell.session_paths import session_file

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
    if manager.session_type == "orchestrator":
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
        manager._state_machine.transition("check_tokens", tokens=manager._last_accumulated_tokens)
    elif state == States.HANDOFF_PENDING:
        _check_deadline(manager, state)
    elif state == States.RESTARTING:
        _check_deadline(manager, state)
    elif state == States.DEAD_CHILD:
        _check_deadline(manager, state)


def _write_merged_and_clear(manager) -> None:
    try:
        cr = json.loads(manager._current_round_path.read_text("utf-8"))
        rid, tids = cr.get("round_id", ""), cr.get("task_ids", [])
    except Exception:
        return
    db = None
    try:
        from agentflow.tools.task_db import TaskDB
        db = TaskDB(manager._project_root / ".agentflow" / "tasks.db")
    except Exception:
        pass
    ep = manager._project_root / "execution_plan.md"
    lock = manager._project_root / "execution_plan.md.lock"
    try:
        with open(lock, "w", encoding="utf-8") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            lines = ep.read_text("utf-8").splitlines(keepends=True)
            changed = False
            for i, ln in enumerate(lines):
                for tid in tids:
                    if re.match(rf"^## Addendum:\s+{re.escape(tid)}", ln) and "(MERGED)" not in ln:
                        lines[i] = ln.rstrip("\n") + " (MERGED)\n"
                        changed = True
                if rid and f"| {rid} |" in ln and "MERGED" not in ln:
                    lines[i] = ln.rstrip("\n").rstrip() + " — MERGED\n"
                    changed = True
            if changed:
                with tempfile.NamedTemporaryFile(mode="w", dir=ep.parent, delete=False, suffix=".tmp", encoding="utf-8") as t:
                    t.write("".join(lines))
                    tmp = t.name
                os.replace(tmp, ep)
    except Exception:
        pass
    try:
        if db:
            db.clear_active_round()
    except Exception:
        pass
    manager._log_audit({"event": "drain_merged_written", "round_id": rid, "task_ids": tids})


def check_drain_restart(manager) -> None:
    """Trigger restart when tasks_in_flight drains and context fill >= 80K."""
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
    tif = manager._tasks_in_flight_path
    if not tif.exists():
        _skip("no_tasks_in_flight_file")
        return
    try:
        tif_content = json.loads(tif.read_text("utf-8"))
        if tif_content:
            _skip("tasks_in_flight_nonempty", tasks=tif_content)
            return
    except Exception as e:
        _skip("tif_read_error", error=str(e))
        return
    threshold = manager._config.get("handoff_primary_tokens", 80000)
    fill_tokens = 0
    try:
        agentflow_dir = manager._project_root / ".agentflow"
        sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
        cf = session_file(agentflow_dir, "context_fill.json", sid)
        if cf.exists():
            data = json.loads(cf.read_text("utf-8"))
            fill_tokens = data.get("fill_tokens", 0)
            ts = data.get("ts")
            if ts is not None and time.time() - ts > 60:
                _skip("fill_stale", ts_age=round(time.time() - ts, 1))
                return
    except Exception as e:
        manager._log_audit({"event": "drain_restart_fill_tokens_read_error", "error": str(e)})
    if fill_tokens < threshold:
        _skip("fill_tokens_below_threshold", fill_tokens=fill_tokens, threshold=threshold)
        return
    manager._log_audit({"event": "drain_restart_triggered", "fill_tokens": fill_tokens, "threshold": threshold})
    _write_merged_and_clear(manager)
    manager._state_machine.transition("restart_session")
