#!/usr/bin/env python3
"""PostToolUse hook (Agent + Bash tools): call pty_signal.py task_done for any
in-flight task that has been marked complete in tasks.json.

Fires after every Agent tool return, and after Bash tool calls that look like
PR merges (command contains 'gh pr merge' or output contains 'Merged pull
request'). The Bash gate avoids a gh API call on every shell invocation.
"""

import fcntl
import json
import re
import subprocess
import sys
from pathlib import Path


def _find_workspace_root() -> Path:
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".agentflow").is_dir(): return parent
    return cwd


def _fetch_merged_pr_titles(limit: int = 20) -> set[str]:
    """Return titles of recently merged PRs via a single gh call."""
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--state", "merged", "--json", "title", "--limit", str(limit)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return {pr["title"] for pr in json.loads(result.stdout)}
    except Exception:
        return set()


def _mark_task_complete(tasks_file: Path, task_id: str) -> bool:
    """Mark task_id as complete using fcntl lock."""
    try:
        with open(tasks_file, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                data = json.load(f)
                for t in data.get("tasks", []):
                    if t.get("task_id") == task_id and t.get("status") == "pending":
                        t["status"] = "complete"
                        f.seek(0)
                        json.dump(data, f)
                        f.truncate()
                        return True
                return False
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except (OSError, ValueError):
        return False


def _run_cleanup(root: Path) -> None:
    """Run cleanup_tasks.py as subprocess."""
    try:
        subprocess.run([sys.executable, str(root / "agentflow" / "tools" / "cleanup_tasks.py"), str(root)], check=False, capture_output=True)
    except Exception:
        pass


def _is_pr_merge_bash(hook_data: dict) -> bool:
    """Check if Bash invocation looks like a PR merge."""
    cmd = hook_data.get("tool_input", {}).get("command", "")
    return "gh pr merge" in cmd or "Merged pull request" in hook_data.get("tool_response", {}).get("output", "")




def _register_pr_url(agentflow_dir: Path, task_id: str, pr_url: str) -> bool:
    """Write/merge {task_id: pr_url} into .agentflow/task_prs.json atomically."""
    prs_file = agentflow_dir / "task_prs.json"
    try:
        mode = "r+" if prs_file.exists() else "w+"
        with open(prs_file, mode) as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                data = json.load(f) if mode == "r+" else {}
                data[task_id] = pr_url
                f.seek(0)
                json.dump(data, f)
                f.truncate()
                return True
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def _check_pr_state(pr_url: str) -> str | None:
    """Call gh pr view <url> --json state; return state string or None on error."""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", pr_url, "--json", "state"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("state")
    except Exception:
        pass
    return None


def _detect_pr_create(hook_data: dict, agentflow_dir: Path) -> None:
    """Detect gh pr create; extract URL and task_id; register PR URL."""
    cmd = hook_data.get("tool_input", {}).get("command", "")
    if "gh pr create" not in cmd:
        return
    output = hook_data.get("tool_response", {}).get("output", "")
    pr_url = next((l.strip() for l in output.strip().split("\n") if l.strip().startswith("https://")), None)
    if not pr_url:
        return

    root = _find_workspace_root()
    task_id = None
    try:
        result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, cwd=root, check=False)
        if result.returncode == 0:
            m = re.search(r"task/(T-\d+)", result.stdout.strip())
            if m:
                task_id = m.group(1)
    except Exception:
        pass

    if not task_id:
        try:
            with open(agentflow_dir / "tasks_in_flight.json") as f:
                in_flight = json.load(f)
            if len(in_flight) == 1:
                task_id = in_flight[0]
        except Exception:
            pass

    if task_id:
        _register_pr_url(agentflow_dir, task_id, pr_url)


def main() -> None:
    try:
        hook_data = json.load(sys.stdin)
    except Exception:
        hook_data = {}

    tool_name = hook_data.get("tool_name", "")
    root = _find_workspace_root()
    agentflow_dir = root / ".agentflow"

    # Register PR URL if gh pr create detected
    if tool_name == "Bash":
        cmd = hook_data.get("tool_input", {}).get("command", "")
        if "gh pr create" in cmd:
            _detect_pr_create(hook_data, agentflow_dir)

    if tool_name == "Bash" and not _is_pr_merge_bash(hook_data):
        sys.exit(0)

    in_flight_file = agentflow_dir / "tasks_in_flight.json"

    if not in_flight_file.exists():
        sys.exit(0)

    try:
        with open(in_flight_file) as f:
            in_flight: list[str] = json.load(f)
    except Exception:
        sys.exit(0)

    if not in_flight:
        sys.exit(0)

    tasks_file = root / "tasks.json"
    if not tasks_file.exists():
        sys.exit(0)

    try:
        with open(tasks_file) as f:
            json.load(f)
    except Exception:
        sys.exit(0)

    task_pr_urls = {}
    try:
        prs_file = agentflow_dir / "task_prs.json"
        if prs_file.exists():
            with open(prs_file) as f:
                task_pr_urls = json.load(f)
    except Exception:
        pass

    merged_titles = _fetch_merged_pr_titles()

    for task_id in in_flight:
        is_merged = False
        if task_id in task_pr_urls:
            is_merged = _check_pr_state(task_pr_urls[task_id]) == "MERGED"
        else:
            is_merged = any(f"{task_id}:" in t or t.startswith(f"{task_id} ") for t in merged_titles)

        if is_merged and _mark_task_complete(tasks_file, task_id):
            _run_cleanup(root)

    # Reload tasks data to pick up any updates written by PR detection above.
    try:
        with open(tasks_file) as f:
            tasks_data = json.load(f)
    except Exception:
        sys.exit(0)

    status_by_id = {t["task_id"]: t.get("status", "pending") for t in tasks_data.get("tasks", [])}

    signal_script = root / "agentflow" / "shell" / "pty_signal.py"

    completed = []
    for task_id in in_flight:
        if status_by_id.get(task_id, "pending") != "pending":
            completed.append(task_id)
            try:
                subprocess.run(
                    [sys.executable, str(signal_script), "task_done", task_id],
                    check=False,
                    capture_output=True,
                )
            except Exception:
                pass

    if completed:
        still_pending = [tid for tid in in_flight if tid not in set(completed)]
        try:
            with open(in_flight_file, "w") as f:
                json.dump(still_pending, f)
        except Exception:
            pass

    sys.exit(0)


if __name__ == "__main__":
    main()
