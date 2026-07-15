#!/usr/bin/env python3
"""UserPromptSubmit hook: clear signal files on /orchestrate and /handoff."""

import fcntl
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agentflow.shell.session_paths import session_file


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
        print(json.dumps({"hook": "user_prompt_submit.py", "event": "check_pr_state_error", "error": str(e), "ts": time.time()}), file=sys.stderr)
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
        print(json.dumps({"hook": "user_prompt_submit.py", "event": "fetch_merged_pr_titles_error", "error": str(e), "ts": time.time()}), file=sys.stderr)
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
    except Exception as e:
        print(json.dumps({"hook": "user_prompt_submit.py", "event": "run_cleanup_error", "error": str(e), "ts": time.time()}), file=sys.stderr)


def _write_session_state_atomic(agentflow_dir: Path, session_type: str, sid: str = "") -> None:
    """Write session_state.json to sessions/<sid>/ if sid, else to root."""
    try:
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        session_state_file = session_file(agentflow_dir, "session_state.json", sid)
        data = {"session_type": session_type}
        # Write to temp file in the same directory for atomic replace
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=session_state_file.parent,
            delete=False,
            suffix=".tmp",
            encoding="utf-8"
        ) as tmp:
            json.dump(data, tmp)
            tmp_path = Path(tmp.name)
        # Atomic replace
        os.replace(tmp_path, session_state_file)
    except Exception as e:
        _log_drain(agentflow_dir, {"event": "write_session_state_error", "error": str(e)})


def _log_drain(agentflow_dir: Path, entry: dict) -> None:
    import time
    try:
        with open(agentflow_dir / "hook_drain_debug.jsonl", "a") as f:
            f.write(json.dumps({"ts": time.time(), "source": "user_prompt_submit", **entry}) + "\n")
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
    except Exception as e:
        _log_drain(agentflow_dir, {"event": "cleanup_tif_read_prs_error", "error": str(e)})

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
        except Exception as e:
            _log_drain(agentflow_dir, {"event": "cleanup_tif_write_error", "error": str(e)})


def main() -> None:
    prompt = None

    # Read the prompt from standard input JSON context if not a TTY
    if not sys.stdin.isatty():
        try:
            data = json.load(sys.stdin)
            if isinstance(data, dict):
                prompt = data.get("prompt")
        except (json.JSONDecodeError, Exception) as e:
            print(json.dumps({"hook": "user_prompt_submit.py", "event": "read_prompt_error", "error": str(e), "ts": time.time()}), file=sys.stderr)

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
    sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
    if prompt:
        if "/orchestrate" in prompt:
            _write_session_state_atomic(agentflow_dir, "orchestrator", sid=sid)
        elif "/oracle" in prompt:
            _write_session_state_atomic(agentflow_dir, "oracle", sid=sid)

    # If the prompt contains "/orchestrate" or "/handoff":
    if prompt and ("/orchestrate" in prompt or "/handoff" in prompt):
        # Delete session-scoped handoff_complete and task_complete if they exist.
        # handoff_complete is namespaced by session ID to prevent cross-session contamination.
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        hc_name = f"handoff_complete_{sid}.json" if sid else "handoff_complete.json"
        for name in (hc_name, "task_complete.json"):
            complete_file = agentflow_dir / name
            try:
                if complete_file.exists():
                    complete_file.unlink()
            except Exception as e:
                _log_drain(agentflow_dir, {"event": "delete_signal_file_error", "error": str(e), "file": name})

    # If the prompt is exactly "/clear" (slash command, not prose), write the clear signal file
    if prompt and prompt.strip() == "/clear":
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        clear_signal_file = agentflow_dir / "clear_signal"
        try:
            clear_signal_file.touch(exist_ok=True)
        except Exception as e:
            _log_drain(agentflow_dir, {"event": "touch_clear_signal_error", "error": str(e)})

    # Clean up merged in-flight tasks
    _cleanup_merged_in_flight(agentflow_dir, sid=sid)

    # Emit session type into every turn so skills never need to infer it.
    try:
        session_type = "unknown"
        ss = session_file(agentflow_dir, "session_state.json", sid)
        if ss.exists():
            st = json.loads(ss.read_text())
            session_type = st.get("session_type") or "unknown"
        print(f"<agentflow-reminder>[SESSION: {session_type}]</agentflow-reminder>")
    except Exception as e:
        print(json.dumps({"hook": "user_prompt_submit.py", "event": "session_type_error", "error": str(e), "ts": time.time()}), file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
