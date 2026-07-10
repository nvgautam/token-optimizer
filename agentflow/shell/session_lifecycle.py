"""Session lifecycle helpers extracted from session_manager — threshold sync, audit logging, session file update."""
from __future__ import annotations
import datetime
import json
import os
import pathlib


def apply_session_threshold(manager) -> None:
    """Apply session-type-specific token threshold to state machine."""
    if manager.session_type == "oracle":
        threshold = manager._config.get("oracle_threshold_tokens", 50000)
    elif manager.session_type == "orchestrator":
        threshold = manager._config.get("handoff_primary_tokens", 80000)
    else:
        return
    if manager._state_machine.threshold_tokens != threshold:
        manager._state_machine.threshold_tokens = threshold


def sync_session_type(manager) -> None:
    """Detect and cache session type from env/files."""
    if manager.session_type is None:
        sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
        filenames = ([f"session_state_{sid}.json"] if sid else []) + ["session_state.json", "session_type"]
        for fname in filenames:
            try:
                fp = manager._project_root / ".agentflow" / fname
                if not fp.exists():
                    continue
                if fname == "session_type":
                    st = fp.read_text("utf-8").strip()
                else:
                    data = json.loads(fp.read_text("utf-8"))
                    st = data.get("session_type", "") if isinstance(data, dict) else ""
                if st in ("oracle", "orchestrator"):
                    manager.session_type = st
                    update_session_file(manager)
                    apply_session_threshold(manager)
                    return
            except Exception:
                pass
    apply_session_threshold(manager)


def update_session_file(manager) -> None:
    """Update ~/.agentflow/sessions/{sid}.json with current session metadata."""
    sid = os.environ.get("AGENTFLOW_SESSION_ID")
    if not sid:
        return
    sf = pathlib.Path.home() / ".agentflow" / "sessions" / f"{sid}.json"
    try:
        data = json.loads(sf.read_text("utf-8")) if sf.exists() else {}
    except Exception:
        data = {}
    try:
        data.setdefault("started_at", datetime.datetime.now().isoformat())
        data.update({"arm": manager._arm, "session_type": manager.session_type})
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def log_audit(manager, entry: dict) -> None:
    """Append audit log entry to ~/.agentflow/pty_audit.jsonl."""
    lp = manager._project_root / ".agentflow" / "pty_audit.jsonl"
    if not lp.parent.exists():
        return
    try:
        entry = {**entry, "ts": datetime.datetime.now().isoformat(), "session_id": os.environ.get("AGENTFLOW_SESSION_ID")}
        with open(lp, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def check_drain_restart(manager) -> None:
    """Trigger restart if tasks_in_flight drains to empty and context ≥ 80K.

    Conditions (all must be true):
    1. session_type == "orchestrator"
    2. state machine is IDLE
    3. not in handoff and handoff not disabled
    4. tasks_in_flight is absent or contains empty list
    5. current_round.json exists (prevents spurious startup trigger)
    6. fill_tokens ≥ handoff_primary_tokens (default 80000)
    """
    from agentflow.shell.state_machine import States

    # Condition 1: orchestrator session
    if manager.session_type != "orchestrator":
        return

    # Condition 2: IDLE state
    if manager._state_machine.state != States.IDLE:
        return

    # Condition 3: handoff not in progress and not disabled
    if manager._handoff_in_progress or manager._auto_handoff_disabled():
        return

    # Condition 5: current_round.json must exist
    if not manager._current_round_path.exists():
        return

    # Condition 4: tasks_in_flight absent or empty
    tasks_in_flight_path = manager._project_root / ".agentflow" / "tasks_in_flight.json"
    try:
        if tasks_in_flight_path.exists():
            tasks = json.loads(tasks_in_flight_path.read_text("utf-8"))
            if tasks:  # non-empty list means tasks still in flight
                return
    except Exception:
        return

    # Condition 6: fill_tokens >= threshold
    threshold = manager._config.get("handoff_primary_tokens", 80000)
    context_fill_path = manager._project_root / ".agentflow" / "context_fill.json"
    fill_tokens = 0
    try:
        if context_fill_path.exists():
            data = json.loads(context_fill_path.read_text("utf-8"))
            fill_tokens = data.get("fill_tokens", 0)
    except Exception:
        pass

    if fill_tokens < threshold:
        return

    # All conditions met: trigger drain restart
    manager.trigger_handoff(trigger="drain")
    manager._log_audit({"event": "drain_restart_triggered", "fill_tokens": fill_tokens, "threshold": threshold})
