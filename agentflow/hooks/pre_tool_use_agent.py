#!/usr/bin/env python3
"""PreToolUse Agent hook: extract task_id from prompt Addendum header and signal task_start."""

import json
import re
import subprocess
import sys
import time
from pathlib import Path


def _find_workspace_root() -> Path:
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".agentflow").is_dir():
            return parent
    return cwd


def main() -> None:
    try:
        hook_data = json.load(sys.stdin)
    except Exception as e:
        print(json.dumps({"hook": "pre_tool_use_agent.py", "event": "load_stdin_error", "error": str(e), "ts": time.time()}), file=sys.stderr)
        sys.exit(0)

    prompt = hook_data.get("tool_input", {}).get("prompt", "")
    if not prompt:
        sys.exit(0)

    m = re.search(r'^## Addendum: (T-\d+)', prompt, re.MULTILINE)
    if not m:
        sys.exit(0)

    task_id = m.group(1)
    root = _find_workspace_root()
    signal_script = root / "agentflow" / "shell" / "pty_signal.py"
    try:
        subprocess.run(
            [sys.executable, str(signal_script), "task_start", task_id],
            check=False,
            capture_output=True,
        )
    except Exception as e:
        print(json.dumps({"hook": "pre_tool_use_agent.py", "event": "task_start_signal_error", "error": str(e), "task_id": task_id, "ts": time.time()}), file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
