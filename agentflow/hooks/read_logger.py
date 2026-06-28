#!/usr/bin/env python3
"""PreToolUse hook: silently log Read calls to .agentflow/shadow_reads.jsonl."""

import hashlib
import json
import os
import sys
from datetime import datetime
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

    cwd = os.getcwd()
    cwd_hash = hashlib.sha256(cwd.encode()).hexdigest()

    try:
        rel = str(Path(file_path).relative_to(cwd))
    except ValueError:
        sys.exit(0)

    idx_path = (
        Path.home() / ".agentflow" / "cache" / cwd_hash / "index" / f"{rel}.idx"
    )
    idx_exists = idx_path.exists()
    idx_sections = len(idx_path.read_text().strip().splitlines()) if idx_exists else 0

    try:
        content = Path(file_path).read_text()
        file_lines = len(content.splitlines())
        file_chars = len(content)
    except OSError:
        file_lines = 0
        file_chars = 0

    entry = {
        "ts": datetime.now().isoformat(),
        "rel": rel,
        "offset": tool_input.get("offset"),
        "limit": tool_input.get("limit"),
        "idx_exists": idx_exists,
        "idx_sections": idx_sections,
        "file_lines": file_lines,
        "file_chars": file_chars,
    }

    log_path = Path(cwd) / ".agentflow" / "shadow_reads.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
