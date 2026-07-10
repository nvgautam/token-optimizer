"""Output handling and token tracking logic extracted from session_manager."""
from __future__ import annotations
import os
import re
import time
import datetime
import json
import pathlib
from agentflow.shell.state_machine import States

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

    detected_path = detect_read_path(clean)
    if detected_path and detected_path.startswith("/"):
        cwd = os.getcwd() + "/"
        detected_path = detected_path[len(cwd):] if detected_path.startswith(cwd) else None
    if detected_path and detected_path != manager._last_idx_injected:
        manager._last_idx_injected = detected_path

    if "/clear" in text:
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

    if manager.session_type is None:
        new_st = "oracle" if "/oracle" in text else "orchestrator" if "/orchestrate" in text else None
        if new_st:
            manager._log_audit({"event": "session_type_transition", "old": manager.session_type, "new": new_st})
            manager.session_type, manager._turn_count, manager._arm = new_st, 0, manager._read_arm_file()
            manager._update_session_file()

    if "/handoff" in text:
        if not manager._manual_handoff:
            manager._manual_handoff = True
            manager._log_audit({"event": "manual_handoff_set"})

    if manager._state_machine.state == States.HANDOFF_PENDING and "HANDOFF_COMPLETE" in clean:
        try:
            manager._handoff_complete_path.parent.mkdir(parents=True, exist_ok=True)
            manager._handoff_complete_path.write_text(json.dumps({"status": "complete"}), encoding="utf-8")
        except Exception:
            pass
        manager._state_machine.transition("handoff_complete_written")

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

    if "HANDOFF RECOMMENDED" in clean:
        if not manager._manual_handoff and not manager._auto_handoff_disabled() and manager._state_machine.state not in (States.HANDOFF_PENDING, States.RESTARTING):
            try:
                tasks_path = manager._project_root / "tasks.json"
                if tasks_path.exists():
                    data = json.loads(tasks_path.read_text("utf-8"))
                    completed = {t["task_id"] for t in data.get("tasks", []) if t.get("status") == "complete"}
                    for tid in list(manager._task_start_tokens):
                        if tid in completed:
                            manager._task_start_tokens.pop(tid)
                            manager._log_audit({"event": "handoff_recommended_evict", "task_id": tid})
            except Exception:
                pass
            primary = manager._config["handoff_primary_tokens"]
            if total >= primary and not bool(manager._task_start_tokens) and manager.session_type != "orchestrator":
                manager.trigger_handoff(trigger="handoff-recommended-stall-recovery")

    _restart_cooldown = 30.0
    _since_restart = time.monotonic() - manager._last_restart_ts
    if not manager._manual_handoff and not manager._auto_handoff_disabled() and manager._state_machine.state not in (States.HANDOFF_PENDING, States.RESTARTING) and _since_restart >= _restart_cooldown:
        primary = manager._config["handoff_primary_tokens"]
        manager._log_audit({"event": "token_evaluation", "accumulated_tokens": total, "primary": primary})

        # T-151: only trigger on 80K + task just completed + no task in-flight.
        # Safety and ceiling triggers removed — they caused mid-task restart storms
        # with no recovery path.
        task_just_completed = complete_m is not None
        task_in_flight = bool(manager._task_start_tokens) or manager._state_machine.state == States.TASK_RUNNING
        if total >= primary and task_just_completed and not task_in_flight:
            manager.trigger_handoff(trigger="auto-primary")

