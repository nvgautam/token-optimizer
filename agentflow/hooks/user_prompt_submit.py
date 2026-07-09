#!/usr/bin/env python3
"""UserPromptSubmit hook: reset accumulator and clear signal files on /orchestrate."""

import json
import os
import sys
import tempfile
from pathlib import Path


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

    sys.exit(0)


if __name__ == "__main__":
    main()
