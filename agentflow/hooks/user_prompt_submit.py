#!/usr/bin/env python3
"""UserPromptSubmit hook: reset accumulator and clear signal files on /orchestrate."""

import fcntl
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


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
    except Exception:
        pass
    return None


def _fetch_merged_pr_titles(limit: int = 20) -> set[str]:
    """Return titles of recently merged PRs via a single gh call."""
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--state", "merged", "--json", "title", "--limit", str(limit)],
            capture_output=True, text=True, timeout=5, check=False,
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


def _write_session_state_atomic(agentflow_dir: Path, session_type: str) -> None:
    """Write session_state.json atomically using temp file + replace."""
    try:
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        session_state_file = agentflow_dir / "session_state.json"
        data = {"session_type": session_type}
        # Write to temp file in the same directory for atomic replace
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=agentflow_dir,
            delete=False,
            suffix=".tmp",
            encoding="utf-8"
        ) as tmp:
            json.dump(data, tmp)
            tmp_path = Path(tmp.name)
        # Atomic replace
        os.replace(tmp_path, session_state_file)
    except Exception:
        pass


def _cleanup_merged_in_flight(agentflow_dir: Path) -> None:
    """Clean up merged tasks from tasks_in_flight.json and mark complete in tasks.json."""
    in_flight_file = agentflow_dir / "tasks_in_flight.json"
    if not in_flight_file.exists():
        return
    try:
        with open(in_flight_file) as f:
            in_flight: list[str] = json.load(f)
    except Exception:
        return
    if not in_flight:
        return

    # Find project root (parent of .agentflow dir)
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
    except Exception:
        pass

    # Fetch merged PR titles only once (fallback for tasks without registered URL)
    merged_titles: set[str] | None = None

    completed = []
    for task_id in in_flight:
        is_merged = False
        if task_id in task_pr_urls:
            is_merged = _check_pr_state(task_pr_urls[task_id]) == "MERGED"
        else:
            if merged_titles is None:
                merged_titles = _fetch_merged_pr_titles()
            is_merged = any(f"{task_id}:" in t or t.startswith(f"{task_id} ") for t in merged_titles)
        if is_merged:
            if _mark_task_complete(tasks_file, task_id):
                _run_cleanup(root)
            completed.append(task_id)

    if completed:
        still_pending = [tid for tid in in_flight if tid not in set(completed)]
        try:
            with open(in_flight_file, "w") as f:
                json.dump(still_pending, f)
        except Exception:
            pass


def main() -> None:
    prompt = None

    # Read the prompt from standard input JSON context if not a TTY
    if not sys.stdin.isatty():
        try:
            data = json.load(sys.stdin)
            if isinstance(data, dict):
                prompt = data.get("prompt")
        except (json.JSONDecodeError, Exception):
            pass

    # If not found or stdin is not a TTY/empty, fallback to sys.argv[1:]
    if prompt is None:
        prompt = " ".join(sys.argv[1:])

    # Locate the project .agentflow directory
    project_root = os.environ.get("AGENTFLOW_PROJECT_ROOT", "")
    if project_root:
        agentflow_dir = Path(project_root) / ".agentflow"
    else:
        agentflow_dir = Path.cwd() / ".agentflow"

    # Write session_state.json for /orchestrate and /oracle
    if prompt:
        if "/orchestrate" in prompt:
            _write_session_state_atomic(agentflow_dir, "orchestrator")
        elif "/oracle" in prompt:
            _write_session_state_atomic(agentflow_dir, "oracle")

    # If the prompt contains "/orchestrate" or "/handoff":
    if prompt and ("/orchestrate" in prompt or "/handoff" in prompt):
        # Write the reset signal file
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        reset_file = agentflow_dir / "reset_accumulator"
        try:
            reset_file.touch(exist_ok=True)
        except Exception:
            pass

        # Delete handoff_complete.json and task_complete.json if they exist
        for name in ("handoff_complete.json", "task_complete.json"):
            complete_file = agentflow_dir / name
            try:
                if complete_file.exists():
                    complete_file.unlink()
            except Exception:
                pass

    # Clean up merged in-flight tasks
    _cleanup_merged_in_flight(agentflow_dir)

    # Emit session type into every turn so skills never need to infer it.
    try:
        ss = agentflow_dir / "session_state.json"
        if ss.exists():
            st = json.loads(ss.read_text())
            session_type = st.get("session_type") or "unknown"
        else:
            session_type = "unknown"
        print(f"<agentflow-reminder>[SESSION: {session_type}]</agentflow-reminder>")
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
