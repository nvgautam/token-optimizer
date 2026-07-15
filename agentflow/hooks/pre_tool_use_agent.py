#!/usr/bin/env python3
"""PreToolUse Agent hook: extract task_id from prompt Addendum header and signal task_start."""

import json
import re
import subprocess
import sys
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
    except Exception:
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
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
