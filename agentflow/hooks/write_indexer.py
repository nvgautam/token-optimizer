#!/usr/bin/env python3
"""PostToolUse hook: regenerate .idx after Write/Edit on Python/Markdown files."""

import json
import sys
from pathlib import Path


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        file_path = data.get("tool_input", {}).get("file_path")
        if not file_path:
            sys.exit(0)

        path = Path(file_path)
        if path.suffix not in (".py", ".md"):
            sys.exit(0)

        try:
            contents = path.read_text(encoding="utf-8")
        except OSError:
            sys.exit(0)

        if len(contents.splitlines()) < 50:
            sys.exit(0)

        from agentflow.indexer.index_manager import update
        update(path, contents)
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
