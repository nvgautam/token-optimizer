"""PostToolUse hook: reads transcript fill tokens and writes context_fill.json mid-turn.

Fires after every tool call so fill_tokens is current when PTY check_drain_restart
runs on the next IDLE event — eliminates the stale-value race from the Stop hook.
"""
from __future__ import annotations
import json
import os
import pathlib
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
    try:
        payload = json.loads(sys.stdin.read())

        project_root = pathlib.Path(
            os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
        )
        agentflow_dir = project_root / ".agentflow"
        agentflow_dir.mkdir(parents=True, exist_ok=True)

        sync_tasks_in_flight(
            payload.get("tool_name", ""),
            payload.get("tool_input", {}),
            agentflow_dir,
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
