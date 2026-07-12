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


def main() -> None:
    """Entry point — always exits 0 to avoid blocking Claude."""
    try:
        payload = json.loads(sys.stdin.read())
        transcript_path = payload.get("transcript_path", "")

        fill_tokens = extract_fill_from_transcript(transcript_path)
        if fill_tokens is None:
            sys.exit(0)

        project_root = pathlib.Path(
            os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
        )
        agentflow_dir = project_root / ".agentflow"
        agentflow_dir.mkdir(parents=True, exist_ok=True)

        fill_path = agentflow_dir / "context_fill.json"
        data_str = json.dumps({"fill_tokens": fill_tokens, "ts": time.time()})

        fd, tmp_path = tempfile.mkstemp(dir=str(agentflow_dir))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data_str)
            os.replace(tmp_path, str(fill_path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
