#!/usr/bin/env python3
"""PreToolUse hook: surface targeted read hints before full-file reads."""

import hashlib
import json
import os
import sys
from pathlib import Path


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path")
    offset = tool_input.get("offset")

    if not file_path or offset is not None:
        sys.exit(0)

    cwd = os.getcwd()
    cwd_hash = hashlib.sha256(cwd.encode()).hexdigest()

    try:
        rel = Path(file_path).relative_to(cwd)
    except ValueError:
        sys.exit(0)

    idx_path = (
        Path.home()
        / ".agentflow"
        / "cache"
        / cwd_hash
        / "index"
        / f"{rel}.idx"
    )

    if idx_path.exists():
        print(f"Optimization available: use targeted read parameters for {rel}")

    sys.exit(0)


if __name__ == "__main__":
    main()
