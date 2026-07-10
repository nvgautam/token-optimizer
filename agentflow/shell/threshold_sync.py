"""Session-type detection and per-type threshold routing for the PTY state machine."""
from __future__ import annotations
import json
import os


def apply_session_threshold(manager) -> None:
    if manager.session_type == "oracle":
        threshold = manager._config.get("oracle_threshold_tokens", 50000)
    elif manager.session_type == "orchestrator":
        threshold = manager._config.get("handoff_primary_tokens", 80000)
    else:
        return
    if manager._state_machine.threshold_tokens != threshold:
        manager._state_machine.threshold_tokens = threshold


def sync_session_type(manager) -> None:
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
                    from agentflow.shell.session_audit import update_session_file
                    update_session_file(manager)
                    apply_session_threshold(manager)
                    return
            except Exception:
                pass
    apply_session_threshold(manager)
