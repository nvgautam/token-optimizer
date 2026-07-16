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
from agentflow.tools.task_db import TaskDB
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
    except Exception as e:
        print(json.dumps({"hook": "post_tool_use_agent.py", "event": "fetch_merged_pr_titles_error", "error": str(e), "ts": time.time()}), file=sys.stderr)
        return set()


def _mark_task_complete(tasks_file: Path, task_id: str) -> str:
    """Mark task_id complete using SQLite. Returns: 'marked'|'already_complete'|'not_found'|'error'."""
    try:
        agentflow_dir = tasks_file.parent / ".agentflow"
        db = TaskDB(agentflow_dir / "tasks.db", tasks_json_path=tasks_file)
        return db.mark_complete(task_id)
    except Exception as e:
        return f"error:{e}"


def _run_cleanup(root: Path) -> None:
    try:
        subprocess.run([sys.executable, str(root / "agentflow" / "tools" / "cleanup_tasks.py"), str(root)],
                       check=False, capture_output=True)
    except Exception as e:
        print(json.dumps({"hook": "post_tool_use_agent.py", "event": "run_cleanup_error", "error": str(e), "ts": time.time()}), file=sys.stderr)


def _is_pr_merge_bash(hook_data: dict) -> bool:
    cmd = hook_data.get("tool_input", {}).get("command", "")
    return "gh pr merge" in cmd or "Merged pull request" in hook_data.get("tool_response", {}).get("output", "")


def _register_pr_url(agentflow_dir: Path, task_id: str, pr_url: str) -> bool:
    """Record PR URL for task_id in .agentflow/task_prs.json (atomic write)."""
    import tempfile
    prs_file = agentflow_dir / "task_prs.json"
    try:
        data: dict = {}
        if prs_file.exists():
            try:
                data = json.loads(prs_file.read_text())
            except Exception:
                data = {}
        data[task_id] = pr_url
        with tempfile.NamedTemporaryFile(
            mode="w", dir=agentflow_dir, delete=False, suffix=".tmp", encoding="utf-8"
        ) as tmp:
            json.dump(data, tmp)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, prs_file)
        return True
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def _check_pr_state(pr_url: str) -> str | None:
    try:
        r = subprocess.run(["gh", "pr", "view", pr_url, "--json", "state"],
                           capture_output=True, text=True, timeout=5, check=False)
        if r.returncode == 0:
            return json.loads(r.stdout).get("state")
    except Exception as e:
        print(json.dumps({"hook": "post_tool_use_agent.py", "event": "check_pr_state_error", "error": str(e), "ts": time.time()}), file=sys.stderr)
    return None


def _handle_pr_merge(cmd: str, in_flight: list[str], agentflow_dir: Path, root: Path, tasks_file: Path) -> None:
    """Direct path: extract all PR numbers from gh pr merge N [M...], call gh pr view for each, handle MERGED/OPEN."""
    m = re.search(r'gh pr merge\s+(.*)', cmd)
    if not m:
        return
    pr_nums = re.findall(r'\d+', m.group(1))

    for pr_num in pr_nums:
        try:
            r = subprocess.run(
                ["gh", "pr", "view", pr_num, "--json", "url,title,state"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            if r.returncode != 0:
                continue
            data = json.loads(r.stdout)
        except Exception as e:
            print(json.dumps({"hook": "post_tool_use_agent.py", "event": "handle_pr_merge_view_error", "error": str(e), "pr_num": pr_num, "ts": time.time()}), file=sys.stderr)
            continue

        url = data.get("url", "")
        title = data.get("title", "")
        state = data.get("state", "")

        tm = re.search(r'\b(T-\d+)\b', title)
        task_id = tm.group(1) if tm else (in_flight[0] if len(in_flight) == 1 else None)
        if not task_id:
            continue
        _log(agentflow_dir, {"event": "pr_merge_direct", "pr_num": pr_num, "task_id": task_id, "state": state})

        if state == "MERGED":
            result = _mark_task_complete(tasks_file, task_id)
            if result in ("marked", "already_complete"):
                _run_cleanup(root)
            try:
                signal_script = root / "agentflow" / "shell" / "pty_signal.py"
                subprocess.run(
                    [sys.executable, str(signal_script), "task_done", task_id],
                    check=False, capture_output=True,
                )
            except Exception as e:
                _log(agentflow_dir, {"event": "handle_pr_merge_signal_error", "error": str(e), "task_id": task_id})
        elif state == "OPEN":
            _register_pr_url(agentflow_dir, task_id, url)


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
    _log(agentflow_dir, {"event": "hook_fired", "tool": tool_name, "is_merge_trigger": is_merge_trigger, "cmd": hook_data.get("tool_input", {}).get("command", "")[:80]})

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
            is_merged = any(f"{task_id}:" in t or t.startswith(f"{task_id} ") for t in merged_titles)
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
        except Exception as e:
            _log(agentflow_dir, {"event": "drain_write_in_flight_error", "error": str(e)})

    drain_elapsed = time.time() - drain_start_time
    _log(agentflow_dir, {"event": "drain_complete", "completed_count": len(completed), "elapsed": drain_elapsed, "total_tasks": len(in_flight)})
    if still_in_flight:
        _log(agentflow_dir, {"event": "drain_partial", "still_in_flight": still_in_flight, "completed_count": len(completed)})

    sys.exit(0)

if __name__ == "__main__":
    main()
