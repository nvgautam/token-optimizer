#!/usr/bin/env python3
"""PostToolUse hook (Agent tool): call pty_signal.py task_done for any in-flight
task that has been marked complete in tasks.json.

Fires after every Agent tool return. Eliminates reliance on LLM compliance
for emitting AGENTFLOW_TASK_COMPLETE signals.
"""

import fcntl
import json
import subprocess
import sys
from pathlib import Path


def _find_workspace_root() -> Path:
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".agentflow").is_dir():
            return parent
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
    """Mark task_id as complete using an exclusive fcntl lock.

    Returns True if the task was found with status 'pending' and updated.
    Returns False if the task is not found, already complete, or the lock
    cannot be acquired.
    """
    try:
        with open(tasks_file, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                data = json.load(f)
                updated = False
                for t in data.get("tasks", []):
                    if t.get("task_id") == task_id and t.get("status") == "pending":
                        t["status"] = "complete"
                        updated = True
                        break
                if not updated:
                    return False
                f.seek(0)
                json.dump(data, f)
                f.truncate()
                return True
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except (OSError, ValueError):
        return False


def _run_cleanup(root: Path) -> None:
    """Run cleanup_tasks.py as a subprocess. Errors are silently ignored."""
    cleanup_script = root / "agentflow" / "tools" / "cleanup_tasks.py"
    try:
        subprocess.run(
            [sys.executable, str(cleanup_script), str(root)],
            check=False,
            capture_output=True,
        )
    except Exception:
        pass


def main() -> None:
    # Consume stdin (required by hook protocol) but we don't need the content.
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    root = _find_workspace_root()
    agentflow_dir = root / ".agentflow"
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

    # PR detection: one gh call fetches all recently merged PR titles; match
    # locally against in-flight task IDs so we never make N API calls.
    merged_titles = _fetch_merged_pr_titles()
    for task_id in in_flight:
        if any(f"{task_id}:" in title or title.startswith(f"{task_id} ") for title in merged_titles):
            if _mark_task_complete(tasks_file, task_id):
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
