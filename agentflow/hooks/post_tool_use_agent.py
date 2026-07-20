#!/usr/bin/env python3
"""PostToolUse hook (Agent + Bash): task_done signal + tasks_in_flight drain.
Debug log: .agentflow/hook_drain_debug.jsonl — one JSON line per hook firing.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agentflow.shell.session_paths import session_file
from agentflow.hooks.post_tool_use_pr import (
    _fetch_merged_pr_titles,
    _is_pr_merge_bash,
    _register_pr_url,  # noqa: F401
    _check_pr_state,
    _handle_pr_merge,
)


def _find_workspace_root() -> Path:
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".agentflow").is_dir():
            # Skip .agentflow inside .claude/worktrees/ — it's a worktree copy
            if ".claude/worktrees" in str(parent):
                continue
            return parent
    return cwd


def _log(agentflow_dir: Path, entry: dict) -> None:
    try:
        with open(agentflow_dir / "hook_drain_debug.jsonl", "a") as f:
            f.write(json.dumps({"ts": time.time(), **entry}) + "\n")
    except Exception:
        pass


def _mark_task_complete(tasks_file: Path, task_id: str) -> str:
    """Mark task_id complete using tasks.json. Returns: 'marked'|'already_complete'|'not_found'|'error'."""
    import fcntl
    import tempfile
    agentflow_dir = tasks_file.parent / ".agentflow"
    lock_path = agentflow_dir / "tasks.json.lock"
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                if not tasks_file.exists():
                    return "not_found"
                data = json.loads(tasks_file.read_text())
                found = False
                for task in data.get("tasks", []):
                    if task.get("task_id") == task_id:
                        if task.get("status") == "complete":
                            return "already_complete"
                        task["status"] = "complete"
                        found = True
                        break
                if not found:
                    return "not_found"
                
                fd, tmp = tempfile.mkstemp(dir=str(tasks_file.parent))
                with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
                    json.dump(data, tmp_f, indent=2)
                os.replace(tmp, str(tasks_file))
                return "marked"
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as e:
        return f"error:{e}"


def _run_cleanup(root: Path) -> None:
    try:
        subprocess.run([sys.executable, str(root / "agentflow" / "tools" / "cleanup_tasks.py"), str(root)],
                       check=False, capture_output=True)
    except Exception as e:
        print(json.dumps({"hook": "post_tool_use_agent.py", "event": "run_cleanup_error", "error": str(e), "ts": time.time()}), file=sys.stderr)


def main() -> None:
    try:
        hook_data = json.load(sys.stdin)
    except Exception as e:
        print(json.dumps({"hook": "post_tool_use_agent.py", "event": "load_stdin_error", "error": str(e), "ts": time.time()}), file=sys.stderr)
        hook_data = {}

    tool_name = hook_data.get("tool_name", "")
    root = _find_workspace_root()
    agentflow_dir = root / ".agentflow"
    is_merge_trigger = tool_name == "Agent" or _is_pr_merge_bash(hook_data)
    full_cmd = hook_data.get("tool_input", {}).get("command", "")
    log_entry: dict = {
        "event": "hook_fired",
        "tool": tool_name,
        "is_merge_trigger": is_merge_trigger,
        "cmd": full_cmd[:80],
        "cwd": str(Path.cwd()),
        "resolved_root": str(root),
        "root_is_worktree": ".claude/worktrees" in str(root),
    }
    if is_merge_trigger and full_cmd:
        log_entry["full_cmd"] = full_cmd
    _log(agentflow_dir, log_entry)

    if tool_name == "Bash" and not _is_pr_merge_bash(hook_data):
        sys.exit(0)

    in_flight_file = session_file(agentflow_dir, "tasks_in_flight.json", os.environ.get("AGENTFLOW_SESSION_ID", ""))
    if not in_flight_file.exists():
        sys.exit(0)

    try:
        in_flight: list[str] = json.loads(in_flight_file.read_text())
    except Exception as e:
        _log(agentflow_dir, {"event": "load_in_flight_error", "error": str(e)})
        sys.exit(0)
    if not in_flight:
        sys.exit(0)
    tasks_file = root / "tasks.json"
    if not tasks_file.exists():
        sys.exit(0)
    try:
        json.loads(tasks_file.read_text())
    except Exception as e:
        _log(agentflow_dir, {"event": "load_tasks_file_error", "error": str(e)})
        sys.exit(0)
    if tool_name == "Bash":
        cmd = hook_data.get("tool_input", {}).get("command", "")
        _handle_pr_merge(cmd, in_flight, agentflow_dir, root, tasks_file)
    task_pr_urls = {}
    try:
        prs_file = agentflow_dir / "task_prs.json"
        if prs_file.exists():
            task_pr_urls = json.loads(prs_file.read_text())
    except Exception as e:
        _log(agentflow_dir, {"event": "load_task_prs_error", "error": str(e)})
    merged_titles = _fetch_merged_pr_titles()
    drain_start_time = time.time()
    _log(agentflow_dir, {"event": "drain_start", "in_flight_count": len(in_flight), "in_flight": in_flight})

    pr_states: dict[str, str | None] = {}
    mark_results: dict[str, str] = {}
    for task_id in in_flight:
        if task_id in task_pr_urls:
            state = _check_pr_state(task_pr_urls[task_id])
            pr_states[task_id] = state
            is_merged = state == "MERGED"
        else:
            is_merged = any(re.search(r'(?:feat|fix|chore|refactor)\(' + re.escape(task_id) + r'\)', t) for t in merged_titles)
            pr_states[task_id] = "title_match" if is_merged else "no_url_no_title_match"

        if is_merged:
            result = _mark_task_complete(tasks_file, task_id)
            mark_results[task_id] = result
            if result in ("marked", "already_complete"):
                _run_cleanup(root)
    try:
        tasks_data = json.loads(tasks_file.read_text())
    except Exception as e:
        _log(agentflow_dir, {"event": "reload_tasks_file_error", "error": str(e)})
        sys.exit(0)

    status_by_id = {t["task_id"]: t.get("status", "pending") for t in tasks_data.get("tasks", [])}
    signal_script = root / "agentflow" / "shell" / "pty_signal.py"

    completed = []
    signal_results: dict[str, str] = {}
    for task_id in in_flight:
        if status_by_id.get(task_id, "pending") != "pending":
            completed.append(task_id)
            try:
                r = subprocess.run([sys.executable, str(signal_script), "task_done", task_id],
                                   check=False, capture_output=True)
                signal_results[task_id] = "ok" if r.returncode == 0 else f"rc={r.returncode}"
            except Exception as e:
                signal_results[task_id] = f"error:{e}"

    still_in_flight = [tid for tid in in_flight if tid not in set(completed)]
    if completed:
        try:
            with open(in_flight_file, "w") as f:
                json.dump(still_in_flight, f)
            _log(agentflow_dir, {"event": "tif_written", "still_in_flight": still_in_flight})
        except Exception as e:
            _log(agentflow_dir, {"event": "drain_write_in_flight_error", "error": str(e)})

    drain_elapsed = time.time() - drain_start_time
    _log(agentflow_dir, {"event": "drain_complete", "completed_count": len(completed), "elapsed": drain_elapsed, "total_tasks": len(in_flight)})
    if still_in_flight:
        _log(agentflow_dir, {"event": "drain_partial", "still_in_flight": still_in_flight, "completed_count": len(completed)})

    sys.exit(0)


if __name__ == "__main__":
    main()
