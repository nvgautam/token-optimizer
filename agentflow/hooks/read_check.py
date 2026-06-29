#!/usr/bin/env python3
"""PreToolUse hook: block full reads on files that have a section map."""

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
    if not file_path:
        sys.exit(0)

    # Already a targeted read — allow through.
    if tool_input.get("offset") is not None:
        sys.exit(0)

    cwd = os.getcwd()
    try:
        rel = str(Path(file_path).relative_to(cwd))
    except ValueError:
        sys.exit(0)

    cwd_hash = hashlib.sha256(cwd.encode()).hexdigest()
    map_path = (
        Path.home() / ".agentflow" / "cache" / cwd_hash / "index" / f"{rel}.idx"
    )
    if not map_path.exists():
        sys.exit(0)

    sections = map_path.read_text().strip()
    if not sections:
        sys.exit(0)

    print(f"Blocked read of {rel}: use Read(offset=N, limit=M)")
    sys.exit(2)


if __name__ == "__main__":
    main()
