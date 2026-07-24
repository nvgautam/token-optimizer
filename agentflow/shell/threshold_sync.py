"""Session-type detection and per-type threshold routing for the PTY state machine."""
from __future__ import annotations
import json
import os

from agentflow.shell.session_paths import session_file
from agentflow.config.constants import is_oracle_session, is_orchestrate_session


def apply_session_threshold(manager) -> None:
    if is_oracle_session(manager.session_type):
        threshold = manager._config.get("oracle_threshold_tokens", 50000)
    elif is_orchestrate_session(manager.session_type):
        threshold = manager._config.get("handoff_primary_tokens", 80000)
    else:
        return
    if manager._state_machine.threshold_tokens != threshold:
        manager._state_machine.threshold_tokens = threshold


def sync_session_type(manager) -> None:
    sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
    agentflow_dir = manager._project_root / ".agentflow"

    # Try per-SID session_state.json first (new path: sessions/<SID>/session_state.json)
    if sid:
        sid_fp = session_file(agentflow_dir, "session_state.json", sid)
        try:
            if sid_fp.exists():
                data = json.loads(sid_fp.read_text("utf-8"))
                st = data.get("session_type", "") if isinstance(data, dict) else ""
                if is_oracle_session(st) or is_orchestrate_session(st):
                    if manager.session_type != st:
                        manager.session_type = st
                        from agentflow.shell.session_audit import update_session_file
                        update_session_file(manager)
                    apply_session_threshold(manager)
                    return
        except Exception as e:
            manager._log_audit({"event": "sync_session_type_sid_read_error", "error": str(e)})
        # When SID is present, never fall through to root-level fallback
        apply_session_threshold(manager)
        return

    # Fallback: root-level session_state.json, then session_type file (only when no SID)
    for fname in ["session_state.json", "session_type"]:
        try:
            fp = agentflow_dir / fname
            if not fp.exists():
                continue
            if fname == "session_type":
                st = fp.read_text("utf-8").strip()
            else:
                data = json.loads(fp.read_text("utf-8"))
                st = data.get("session_type", "") if isinstance(data, dict) else ""
            if is_oracle_session(st) or is_orchestrate_session(st):
                if manager.session_type != st:
                    manager.session_type = st
                    from agentflow.shell.session_audit import update_session_file
                    update_session_file(manager)
                apply_session_threshold(manager)
                return
        except Exception as e:
            manager._log_audit({"event": "sync_session_type_fallback_read_error", "error": str(e)})
    apply_session_threshold(manager)
