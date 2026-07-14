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
    fd, tmp = tempfile.mkstemp(dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data_str)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def sync_tasks_in_flight(tool_name: str, tool_input: dict, agentflow_dir: pathlib.Path) -> None:
    """When current_round.json is written, populate tasks_in_flight.json from task_ids.

    Absent tif = round not initialized (PTY skips drain check).
    [] tombstone = drained (PTY may restart).
    Non-empty = tasks running (PTY skips drain check).
    """
    if tool_name != "Write":
        return
    if not tool_input.get("file_path", "").endswith("/.agentflow/current_round.json"):
        return
    try:
        task_ids = json.loads(tool_input.get("content", "{}")).get("task_ids", [])
        if not isinstance(task_ids, list) or not task_ids:
            return
        _atomic_write(agentflow_dir / "tasks_in_flight.json", json.dumps(task_ids))
    except Exception:
        pass


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
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
