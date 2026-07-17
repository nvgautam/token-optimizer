"""PostToolUse hook: reads transcript fill tokens and writes context_fill.json mid-turn.

Fires after every tool call so fill_tokens is current when PTY check_drain_restart
runs on the next IDLE event — eliminates the stale-value race from the Stop hook.

Also detects PR merge events and updates tasks.json + execution_plan.md.
"""
from __future__ import annotations
import contextlib
import fcntl
import json
import os
import pathlib
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agentflow.shell.session_paths import session_file


def compute_fill(usage: dict) -> int:
    """Sum the three input token fields; output_tokens not included."""
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
    )


def extract_fill_from_transcript(transcript_path: str) -> int | None:
    """Return fill for the last assistant entry with usage; None if absent."""
    last_fill: int | None = None
    try:
        with open(transcript_path, "r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "assistant":
                    continue
                usage = entry.get("message", {}).get("usage")
                if usage is not None:
                    last_fill = compute_fill(usage)
    except OSError:
        return None
    return last_fill


def _atomic_write(path: pathlib.Path, data_str: str) -> None:
    fd = None
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data_str)
        os.replace(tmp, str(path))
    except Exception as e:
        print(json.dumps({"hook": "post_tool_use.py", "event": "atomic_write_error", "error": str(e), "ts": time.time()}), file=sys.stderr)
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _log(agentflow_dir: pathlib.Path, entry: dict) -> None:
    try:
        with open(agentflow_dir / "hook_drain_debug.jsonl", "a") as f:
            f.write(json.dumps({"ts": time.time(), **entry}) + "\n")
    except Exception:
        pass


@contextlib.contextmanager
def _file_lock(lock_path: pathlib.Path):
    """Acquire an exclusive file lock."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    f = open(lock_path, "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def detect_pr_merge(
    tool_name: str,
    tool_input: dict,
    tool_response: dict,
    agentflow_dir: pathlib.Path,
    project_root: pathlib.Path,
) -> None:
    """Detect PR merge event and update tasks.json + execution_plan.md."""
    if tool_name != "Bash":
        return

    output = ""
    if isinstance(tool_response, dict):
        output = tool_response.get("output", "")
    else:
        output = str(tool_response)

    if "✓ Merged pull request" not in output:
        return

    # Check session_type
    sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
    session_type = "unknown"
    try:
        ss_path = session_file(agentflow_dir, "session_state.json", sid if sid else None)
        if ss_path.exists():
            session_type = json.loads(ss_path.read_text()).get("session_type", "unknown")
    except Exception:
        pass

    if session_type != "orchestrator":
        return

    # Extract task_id from PR title: match conventional commit with task ID
    match = re.search(r'(?:feat|fix|chore|refactor)\((T-\d+)\)', output)
    if not match:
        return

    task_id = match.group(1)

    # Update tasks.json with lock
    tasks_path = project_root / "tasks.json"
    lock_path = agentflow_dir / "tasks.json.lock"

    try:
        with _file_lock(lock_path):
            if tasks_path.exists():
                tasks_data = json.loads(tasks_path.read_text())
                for task in tasks_data.get("tasks", []):
                    if task.get("task_id") == task_id:
                        task["status"] = "complete"
                _atomic_write(tasks_path, json.dumps(tasks_data, indent=2))
    except Exception:
        pass

    # Update execution_plan.md with lock
    ep_path = project_root / "execution_plan.md"
    lock_ep = agentflow_dir / "execution_plan.md.lock"

    try:
        with _file_lock(lock_ep):
            if ep_path.exists():
                lines = ep_path.read_text().split("\n")
                for i, line in enumerate(lines):
                    # Check if this line contains the task_id in a table row or addendum
                    if task_id in line and "MERGED" not in line:
                        # Check if it's a table row
                        if "|" in line:
                            # Append MERGED marker if not already there
                            if not line.rstrip().endswith("MERGED"):
                                lines[i] = line.rstrip() + " — MERGED (auto)"
                        break
                _atomic_write(ep_path, "\n".join(lines))
    except Exception:
        pass


def _sync_tif_from_disk_if_absent(agentflow_dir: pathlib.Path) -> None:
    """Self-healing fallback: populate tif from current_round.json on disk when tif is absent.

    Handles the case where orchestrate writes current_round.json via Bash (not the Write tool),
    so the Write-tool path in sync_tasks_in_flight never fires.
    """
    sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
    tif_path = session_file(agentflow_dir, "tasks_in_flight.json", sid)
    if tif_path.exists():
        return
    cr_path = agentflow_dir / "current_round.json"
    if not cr_path.exists():
        return
    try:
        task_ids = json.loads(cr_path.read_text()).get("task_ids", [])
        if not isinstance(task_ids, list) or not task_ids:
            return
        _atomic_write(tif_path, json.dumps(task_ids))
        _log(agentflow_dir, {"event": "sync_tif_fallback_written", "task_ids": task_ids})
    except Exception as e:
        _log(agentflow_dir, {"event": "sync_tif_fallback_error", "err": str(e)})


def sync_tasks_in_flight(tool_name: str, tool_input: dict, agentflow_dir: pathlib.Path) -> None:
    """When current_round.json is written, populate tasks_in_flight.json from task_ids.

    Absent tif = round not initialized (PTY skips drain check).
    [] tombstone = drained (PTY may restart).
    Non-empty = tasks running (PTY skips drain check).
    """
    file_path = tool_input.get("file_path", "")
    if tool_name != "Write":
        if file_path.endswith("/.agentflow/current_round.json"):
            _log(agentflow_dir, {"event": "sync_tif_skip", "reason": "not_write_tool", "tool": tool_name})
        _sync_tif_from_disk_if_absent(agentflow_dir)
        return
    if not file_path.endswith("/.agentflow/current_round.json"):
        return
    try:
        task_ids = json.loads(tool_input.get("content", "{}")).get("task_ids", [])
        if not isinstance(task_ids, list) or not task_ids:
            _log(agentflow_dir, {"event": "sync_tif_skip", "reason": "no_task_ids"})
            return
        sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
        tif_path = session_file(agentflow_dir, "tasks_in_flight.json", sid)
        _atomic_write(tif_path, json.dumps(task_ids))
        _log(agentflow_dir, {"event": "sync_tif_written", "task_ids": task_ids})
    except Exception as e:
        _log(agentflow_dir, {"event": "sync_tif_error", "err": str(e)})


def main() -> None:
    """Entry point — always exits 0 to avoid blocking Claude."""
    project_root = pathlib.Path(
        os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    )
    agentflow_dir = project_root / ".agentflow"
    try:
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        payload = json.loads(sys.stdin.read())

        sync_tasks_in_flight(
            payload.get("tool_name", ""),
            payload.get("tool_input", {}),
            agentflow_dir,
        )

        detect_pr_merge(
            payload.get("tool_name", ""),
            payload.get("tool_input", {}),
            payload.get("tool_response", {}),
            agentflow_dir,
            project_root,
        )

        transcript_path = payload.get("transcript_path", "")
        fill_tokens = extract_fill_from_transcript(transcript_path)
        if fill_tokens is None:
            sys.exit(0)

        # Read AGENTFLOW_SESSION_ID from env (default to empty string for backward compat)
        sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
        fill_path = session_file(agentflow_dir, "context_fill.json", sid if sid else None)
        _atomic_write(fill_path, json.dumps({"fill_tokens": fill_tokens, "ts": time.time()}))
    except Exception as e:
        _log(agentflow_dir, {"event": "context_fill_write_error", "error": str(e)})
    sys.exit(0)


if __name__ == "__main__":
    main()
