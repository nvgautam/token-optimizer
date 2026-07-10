"""PTY audit logging and session metadata persistence."""
from __future__ import annotations
import datetime
import json
import os
import pathlib


def log_audit(manager, entry: dict) -> None:
    lp = manager._project_root / ".agentflow" / "pty_audit.jsonl"
    if not lp.parent.exists():
        return
    try:
        entry = {**entry, "ts": datetime.datetime.now().isoformat(), "session_id": os.environ.get("AGENTFLOW_SESSION_ID")}
        with open(lp, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def update_session_file(manager) -> None:
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
