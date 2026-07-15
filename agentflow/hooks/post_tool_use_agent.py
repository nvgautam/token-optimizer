#!/usr/bin/env python3
"""PostToolUse hook (Agent + Bash): task_done signal + tasks_in_flight drain.
Debug log: .agentflow/hook_drain_debug.jsonl — one JSON line per hook firing.
"""

import fcntl
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from agentflow.shell.session_paths import session_file


def _find_workspace_root() -> Path:
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".agentflow").is_dir(): return parent
    return cwd


def _log(agentflow_dir: Path, entry: dict) -> None:
    try:
        with open(agentflow_dir / "hook_drain_debug.jsonl", "a") as f:
            f.write(json.dumps({"ts": time.time(), **entry}) + "\n")
    except Exception:
        pass


def _fetch_merged_pr_titles(limit: int = 20) -> set[str]:
    try:
        r = subprocess.run(["gh", "pr", "list", "--state", "merged", "--json", "title", "--limit", str(limit)],
                           capture_output=True, text=True, timeout=5, check=False)
        return {pr["title"] for pr in json.loads(r.stdout)}
    except Exception:
        return set()


def _mark_task_complete(tasks_file: Path, task_id: str) -> str:
    """Mark task_id complete. Returns: 'marked'|'already_complete'|'not_found'|'locked'|'error'."""
    try:
        with open(tasks_file, "r+") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return "locked"
            try:
                data = json.load(f)
                for t in data.get("tasks", []):
                    if t.get("task_id") == task_id:
                        if t.get("status") != "pending":
                            return "already_complete"
                        t["status"] = "complete"
                        f.seek(0); json.dump(data, f); f.truncate()
                        return "marked"
                return "not_found"
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as e:
        return f"error:{e}"


def _run_cleanup(root: Path) -> None:
    try:
        subprocess.run([sys.executable, str(root / "agentflow" / "tools" / "cleanup_tasks.py"), str(root)],
                       check=False, capture_output=True)
    except Exception:
        pass


def _is_pr_merge_bash(hook_data: dict) -> bool:
    cmd = hook_data.get("tool_input", {}).get("command", "")
    return "gh pr merge" in cmd or "Merged pull request" in hook_data.get("tool_response", {}).get("output", "")


def _register_pr_url(agentflow_dir: Path, task_id: str, pr_url: str) -> bool:
    prs_file = agentflow_dir / "task_prs.json"
    try:
        mode = "r+" if prs_file.exists() else "w+"
        with open(prs_file, mode) as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                data = json.load(f) if mode == "r+" else {}
                data[task_id] = pr_url
                f.seek(0); json.dump(data, f); f.truncate(); return True
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def _check_pr_state(pr_url: str) -> str | None:
    try:
        r = subprocess.run(["gh", "pr", "view", pr_url, "--json", "state"],
                           capture_output=True, text=True, timeout=5, check=False)
        if r.returncode == 0:
            return json.loads(r.stdout).get("state")
    except Exception:
        pass
    return None


def _detect_pr_create(hook_data: dict, agentflow_dir: Path) -> None:
    cmd = hook_data.get("tool_input", {}).get("command", "")
    output = hook_data.get("tool_response", {}).get("output", "")
    pr_url = next((l.strip() for l in output.strip().split("\n") if l.strip().startswith("https://")), None)
    if not pr_url:
        _log(agentflow_dir, {"event": "pr_create_no_url", "cmd": cmd[:80], "output_preview": output[:120]})
        return

    root = _find_workspace_root()
    task_id = None
    try:
        r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, cwd=root, check=False)
        if r.returncode == 0:
            m = re.search(r"task/(T-\d+)", r.stdout.strip())
            if m:
                task_id = m.group(1)
    except Exception:
        pass

    if not task_id:
        try:
            with open(session_file(agentflow_dir, "tasks_in_flight.json", os.environ.get("AGENTFLOW_SESSION_ID", ""))) as f:
                in_flight = json.load(f)
            if len(in_flight) == 1:
                task_id = in_flight[0]
        except Exception:
            pass

    registered = _register_pr_url(agentflow_dir, task_id, pr_url) if task_id else False
    _log(agentflow_dir, {"event": "pr_create_detected", "task_id": task_id, "pr_url": pr_url, "registered": registered})


def main() -> None:
    try:
        hook_data = json.load(sys.stdin)
    except Exception:
        hook_data = {}

    tool_name = hook_data.get("tool_name", "")
    root = _find_workspace_root()
    agentflow_dir = root / ".agentflow"

    if tool_name == "Bash":
        cmd = hook_data.get("tool_input", {}).get("command", "")
        if "gh pr create" in cmd:
            _detect_pr_create(hook_data, agentflow_dir)

    is_merge_trigger = tool_name == "Agent" or _is_pr_merge_bash(hook_data)
    _log(agentflow_dir, {"event": "hook_fired", "tool": tool_name, "is_merge_trigger": is_merge_trigger,
                          "cmd": hook_data.get("tool_input", {}).get("command", "")[:80]})

    if tool_name == "Bash" and not _is_pr_merge_bash(hook_data):
        sys.exit(0)

    in_flight_file = session_file(agentflow_dir, "tasks_in_flight.json", os.environ.get("AGENTFLOW_SESSION_ID", ""))
    if not in_flight_file.exists():
        _log(agentflow_dir, {"event": "early_exit", "reason": "no_tasks_in_flight_file"})
        sys.exit(0)

    try:
        in_flight: list[str] = json.loads(in_flight_file.read_text())
    except Exception as e:
        _log(agentflow_dir, {"event": "early_exit", "reason": "tasks_in_flight_read_error", "err": str(e)})
        sys.exit(0)

    if not in_flight:
        _log(agentflow_dir, {"event": "early_exit", "reason": "tasks_in_flight_empty"})
        sys.exit(0)

    tasks_file = root / "tasks.json"
    if not tasks_file.exists():
        _log(agentflow_dir, {"event": "early_exit", "reason": "no_tasks_file"})
        sys.exit(0)

    try:
        json.loads(tasks_file.read_text())
    except Exception as e:
        _log(agentflow_dir, {"event": "early_exit", "reason": "tasks_file_read_error", "err": str(e)})
        sys.exit(0)

    task_pr_urls = {}
    try:
        prs_file = agentflow_dir / "task_prs.json"
        if prs_file.exists():
            task_pr_urls = json.loads(prs_file.read_text())
    except Exception:
        pass
    merged_titles = _fetch_merged_pr_titles()
    _log(agentflow_dir, {"event": "merge_check_start", "in_flight": in_flight,
                          "task_pr_urls_keys": list(task_pr_urls.keys()), "merged_title_count": len(merged_titles)})

    pr_states: dict[str, str | None] = {}
    mark_results: dict[str, str] = {}
    for task_id in in_flight:
        if task_id in task_pr_urls:
            state = _check_pr_state(task_pr_urls[task_id])
            pr_states[task_id] = state
            is_merged = state == "MERGED"
        else:
            is_merged = any(f"{task_id}:" in t or t.startswith(f"{task_id} ") for t in merged_titles)
            pr_states[task_id] = "title_match" if is_merged else "no_url_no_title_match"

        if is_merged:
            result = _mark_task_complete(tasks_file, task_id)
            mark_results[task_id] = result
            if result in ("marked", "already_complete"):
                _run_cleanup(root)

    _log(agentflow_dir, {"event": "merge_check_done", "pr_states": pr_states, "mark_results": mark_results})
    try:
        tasks_data = json.loads(tasks_file.read_text())
    except Exception:
        sys.exit(0)

    status_by_id = {t["task_id"]: t.get("status", "pending") for t in tasks_data.get("tasks", [])}
    signal_script = root / "agentflow" / "shell" / "pty_signal.py"

    completed = []
    signal_results: dict[str, str] = {}
    for task_id in in_flight:
        if status_by_id.get(task_id, "pending") != "pending":
            completed.append(task_id)
            try:
                r = subprocess.run(
                    [sys.executable, str(signal_script), "task_done", task_id],
                    check=False, capture_output=True,
                )
                signal_results[task_id] = "ok" if r.returncode == 0 else f"rc={r.returncode} stderr={r.stderr[:80]}"
            except Exception as e:
                signal_results[task_id] = f"error:{e}"

    still_in_flight = [tid for tid in in_flight if tid not in set(completed)]
    if completed:
        try:
            with open(in_flight_file, "w") as f:
                json.dump(still_in_flight, f)
        except Exception:
            pass

    _log(agentflow_dir, {"event": "drain_done", "completed": completed,
                          "signal_results": signal_results, "still_in_flight": still_in_flight})
    sys.exit(0)


if __name__ == "__main__":
    main()
