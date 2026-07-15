"""Output handling and token tracking logic extracted from session_manager."""
from __future__ import annotations
import os
import re
import time
import datetime
import json
import pathlib
from agentflow.hooks.stop_context_capture import FILL_STALE_SECONDS
from agentflow.shell.session_paths import session_file

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[mGKHFABCDhJlsu]")
_READ_PATH_RE = re.compile(
    r"Read\([^)]*?file_path\s*=\s*[\"']([^\"']+\.(?:py|md|json|toml|yaml|yml|txt))[\"']|"
    r"Read\([\"']([^\s\"')]+\.(?:py|md|json|toml|yaml|yml|txt))[\"']\)|"
    r"(?:^|\b)Read\s+tool\s+[\"']?([^\s\"']+\.(?:py|md|json|toml|yaml|yml|txt))[\"']?",
    re.MULTILINE
)

def ansi_strip(text: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", text)

def detect_read_path(text: str) -> str | None:
    m = _READ_PATH_RE.search(text)
    return next((g for g in m.groups() if g), None) if m else None

def _read_fill_tokens(project_root: pathlib.Path) -> int | None:
    """Return fill_tokens from context_fill.json if fresh (< FILL_STALE_SECONDS old)."""
    try:
        agentflow_dir = project_root / ".agentflow"
        sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
        fill_path = session_file(agentflow_dir, "context_fill.json", sid)
        data = json.loads(fill_path.read_text("utf-8"))
        if time.time() - data["ts"] < FILL_STALE_SECONDS:
            return int(data["fill_tokens"])
    except Exception:
        pass
    return None


def record_task_tokens(manager, task_id: str, delta: int) -> None:
    rp, el, fc = manager._project_root / ".agentflow" / "current_round.json", 0, 0
    try:
        d = json.loads(rp.read_text("utf-8")) if rp.exists() else {}
        el = d.get("estimated_lines_per_task", {}).get(task_id, 0)
        fc = d.get("file_counts_per_task", {}).get(task_id, 0)
    except Exception:
        pass
    log_path = pathlib.Path.home() / ".agentflow" / "task_token_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"task_id": task_id, "session_type": manager.session_type, "token_delta": delta, "estimated_lines": el, "file_count": fc, "timestamp": datetime.datetime.now().isoformat()}
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

def handle_output(manager, chunk: bytes) -> None:
    text = chunk.decode("utf-8", errors="replace")
    clean = ansi_strip(text)
    
    manager.poll()

    # Check for clear_signal file (written by UserPromptSubmit hook when /clear is in prompt)
    clear_signal_path = manager._project_root / ".agentflow" / "clear_signal"
    if clear_signal_path.exists():
        manager._log_audit({"event": "clear_detected"})
        if manager.session_type is not None:
            manager._log_audit({"event": "session_type_transition", "old": manager.session_type, "new": None})
        manager.session_type, manager._turn_count = None, 0
        if manager._manual_handoff:
            manager._manual_handoff = False
            manager._log_audit({"event": "manual_handoff_reset"})
        if hasattr(manager._tokenizer, "reset"):
            manager._tokenizer.reset()
        manager._update_session_file()
        try:
            clear_signal_path.unlink()
        except Exception:
            pass

    detected_path = detect_read_path(clean)
    if detected_path and detected_path.startswith("/"):
        cwd = os.getcwd() + "/"
        detected_path = detected_path[len(cwd):] if detected_path.startswith(cwd) else None
    if detected_path and detected_path != manager._last_idx_injected:
        manager._last_idx_injected = detected_path

    manager._current_turn_output_tokens += manager._tokenizer.count_tokens(text, "claude")
    total = manager._tokenizer.accumulate(text, "claude")
    manager._last_accumulated_tokens = total

    start_m = re.search(r"AGENTFLOW_TASK_START:([A-Za-z0-9_-]+)", clean)
    if start_m:
        manager._task_start_tokens[start_m.group(1)] = total

    complete_m = re.search(r"AGENTFLOW_TASK_COMPLETE:([A-Za-z0-9_-]+)", clean)
    if complete_m:
        tid = complete_m.group(1)
        if tid in manager._task_start_tokens:
            record_task_tokens(manager, tid, total - manager._task_start_tokens.pop(tid))

        # Turn boundary: task completed
        manager._turn_count += 1
        if manager._turn_count == 1:
            manager._arm = manager._read_arm_file()
        manager._turn_output_history.append(manager._current_turn_output_tokens)
        if len(manager._turn_output_history) > 10:
            manager._turn_output_history = manager._turn_output_history[-10:]

        lp = manager._project_root / ".agentflow" / "verbosity_log.jsonl"
        if lp.parent.exists():
            try:
                entry = {"ts": datetime.datetime.now().isoformat(), "session_type": manager.session_type, "turn": manager._turn_count, "output_tokens": manager._current_turn_output_tokens, "arm": manager._arm, "session_id": os.environ.get("AGENTFLOW_SESSION_ID")}
                with open(lp, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry) + "\n")
            except Exception:
                pass
        manager._current_turn_output_tokens = 0
        manager._last_idx_injected = None
        manager._run_stale_index_guard()


