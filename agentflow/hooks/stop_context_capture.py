"""Stop hook: reads transcript fill tokens and writes context_fill.json atomically."""
from __future__ import annotations
import json
import os
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from agentflow.shell.session_paths import session_file

MODEL_CONTEXT_WINDOW = 200_000  # claude-sonnet-4-6 / claude-opus-4
FILL_STALE_SECONDS = 60


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
    except OSError as e:
        print(json.dumps({"hook": "stop_context_capture.py", "event": "extract_fill_error", "error": str(e), "ts": time.time()}), file=sys.stderr)
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

        # Read AGENTFLOW_SESSION_ID from env (default to empty string for backward compat)
        sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
        fill_path = session_file(agentflow_dir, "context_fill.json", sid if sid else None)
        data_str = json.dumps({"fill_tokens": fill_tokens, "ts": time.time()})

        # Atomic write: temp file in same dir as fill_path + os.replace
        fd = None
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(dir=str(fill_path.parent))
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data_str)
            os.replace(tmp_path, str(fill_path))
        except Exception as e:
            print(json.dumps({"hook": "stop_context_capture.py", "event": "atomic_write_error", "error": str(e), "ts": time.time()}), file=sys.stderr)
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
    except Exception as e:
        print(json.dumps({"hook": "stop_context_capture.py", "event": "context_capture_error", "error": str(e), "ts": time.time()}), file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
