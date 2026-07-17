#!/usr/bin/env python3
"""PR/task cleanup module for UserPromptSubmit hook."""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agentflow.shell.session_paths import session_file
from agentflow.tools.task_db import TaskDB


def _check_pr_state(pr_url: str) -> str | None:
    """Call gh pr view <url> --json state; return state string or None on error."""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", pr_url, "--json", "state"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("state")
    except Exception as e:
        print(json.dumps({"hook": "ups_task_sync.py", "event": "check_pr_state_error", "error": str(e), "ts": time.time()}), file=sys.stderr)
    return None


def _fetch_merged_pr_titles(limit: int = 20) -> set[str]:
    """Return titles of recently merged PRs via a single gh call."""
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--state", "merged", "--json", "title", "--limit", str(limit)],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return {pr["title"] for pr in json.loads(result.stdout)}
    except Exception as e:
        print(json.dumps({"hook": "ups_task_sync.py", "event": "fetch_merged_pr_titles_error", "error": str(e), "ts": time.time()}), file=sys.stderr)
        return set()


def _mark_task_complete(tasks_file: Path, task_id: str) -> bool:
    """Mark task_id as complete using SQLite. Returns True if marked or already complete."""
    try:
        agentflow_dir = tasks_file.parent / ".agentflow"
        db = TaskDB(agentflow_dir / "tasks.db", tasks_json_path=tasks_file)
        return db.mark_complete(task_id) in ("marked", "already_complete")
    except Exception:
        return False


def _run_cleanup(root: Path) -> None:
    """Run cleanup_tasks.py as subprocess."""
    try:
        subprocess.run([sys.executable, str(root / "agentflow" / "tools" / "cleanup_tasks.py"), str(root)], check=False, capture_output=True)
    except Exception as e:
        print(json.dumps({"hook": "ups_task_sync.py", "event": "run_cleanup_error", "error": str(e), "ts": time.time()}), file=sys.stderr)


def _locked_write_tasks(tasks_file: Path, agentflow_dir: Path, task_id: str) -> bool:
    """Mark task complete using SQLite atomic transaction and run cleanup."""
    try:
        db = TaskDB(agentflow_dir / "tasks.db", tasks_json_path=tasks_file)
        result = db.mark_complete(task_id)
        if result == "marked":
            root = tasks_file.parent
            _run_cleanup(root)
            return True
        if result == "already_complete":
            return False
        return False
    except Exception as e:
        _log_drain(agentflow_dir, {"event": "locked_write_tasks_error", "error": str(e), "task_id": task_id})
        return False


def _log_drain(agentflow_dir: Path, entry: dict) -> None:
    """Append JSON entry to hook_drain_debug.jsonl."""
    try:
        with open(agentflow_dir / "hook_drain_debug.jsonl", "a") as f:
            f.write(json.dumps({"ts": time.time(), "source": "ups_task_sync", **entry}) + "\n")
    except Exception:
        pass


def _cleanup_merged_in_flight(agentflow_dir: Path, sid: str = "") -> None:
    """Clean up merged tasks from tasks_in_flight.json and mark complete in tasks.json."""
    in_flight_file = session_file(agentflow_dir, "tasks_in_flight.json", sid)
    if not in_flight_file.exists():
        _log_drain(agentflow_dir, {"event": "cleanup_tif_skip", "reason": "no_file"})
        return
    try:
        with open(in_flight_file) as f:
            in_flight: list[str] = json.load(f)
    except Exception as e:
        _log_drain(agentflow_dir, {"event": "cleanup_tif_read_error", "error": str(e)})
        return
    _log_drain(agentflow_dir, {"event": "cleanup_tif_start", "in_flight": in_flight})
    if not in_flight:
        return

    root = agentflow_dir.parent
    tasks_file = root / "tasks.json"
    if not tasks_file.exists():
        return

    task_pr_urls: dict[str, str] = {}
    try:
        prs_file = agentflow_dir / "task_prs.json"
        if prs_file.exists():
            with open(prs_file) as f:
                task_pr_urls = json.load(f)
    except Exception as e:
        _log_drain(agentflow_dir, {"event": "cleanup_tif_read_prs_error", "error": str(e)})

    merged_titles: set[str] | None = None

    completed = []
    for task_id in in_flight:
        is_merged = False
        if task_id in task_pr_urls:
            is_merged = _check_pr_state(task_pr_urls[task_id]) == "MERGED"
        else:
            if merged_titles is None:
                merged_titles = _fetch_merged_pr_titles()
            is_merged = any(re.search(r'(?:feat|fix|chore|refactor)\(' + re.escape(task_id) + r'\)', t) for t in merged_titles)
        if is_merged:
            _locked_write_tasks(tasks_file, agentflow_dir, task_id)
            try:
                signal_script = root / "agentflow" / "shell" / "pty_signal.py"
                subprocess.run(
                    [sys.executable, str(signal_script), "task_done", task_id],
                    check=False, capture_output=True,
                )
            except Exception as e:
                _log_drain(agentflow_dir, {"event": "cleanup_tif_signal_error", "error": str(e), "task_id": task_id})
            completed.append(task_id)

    _log_drain(agentflow_dir, {"event": "cleanup_tif_done", "completed": completed,
                               "still_in_flight": [t for t in in_flight if t not in set(completed)]})
    if completed:
        still_pending = [tid for tid in in_flight if tid not in set(completed)]
        try:
            with open(in_flight_file, "w") as f:
                json.dump(still_pending, f)
            _log_drain(agentflow_dir, {"event": "tif_written", "still_in_flight": still_pending})
        except Exception as e:
            _log_drain(agentflow_dir, {"event": "cleanup_tif_write_error", "error": str(e)})
