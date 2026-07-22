"""PTY audit logging and session metadata persistence."""
from __future__ import annotations
import datetime
import json
import os
import pathlib
import sys

from agentflow.shell.audit_logger import flush_writes, write_audit


def log_audit(manager, entry: dict) -> None:
    lp = manager._project_root / ".agentflow" / "pty_audit.jsonl"
    event = entry.get("event", "unknown")
    source = entry.get("source", "shell")
    level = entry.get("level", "INFO")
    session_type = entry.get("session_type")
    extra = {k: v for k, v in entry.items() if k not in {"event", "source", "level", "session_type"}}
    write_audit(lp, event=event, source=source, level=level, session_type=session_type, **extra)
    flush_writes()


def update_session_file(manager) -> None:
    sid = os.environ.get("AGENTFLOW_SESSION_ID")
    if not sid:
        return
    sf = pathlib.Path.home() / ".agentflow" / "sessions" / f"{sid}.json"
    try:
        data = json.loads(sf.read_text("utf-8")) if sf.exists() else {}
    except Exception as e:
        sys.stderr.write(f"[agentflow] update_session_file read error: {e}\n")
        data = {}
    try:
        data.setdefault("started_at", datetime.datetime.now().isoformat())
        data.update({"arm": manager._arm, "session_type": manager.session_type})
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(json.dumps(data), encoding="utf-8")
    except Exception as e:
        sys.stderr.write(f"[agentflow] update_session_file write error: {e}\n")
