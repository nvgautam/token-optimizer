#!/usr/bin/env python3
"""PostToolUse hook: regenerate .idx after Write/Edit on Python/Markdown files."""

import json
import sys
import time
from pathlib import Path


def main() -> None:
    is_pytest = len(sys.argv) > 0 and ("pytest" in sys.argv[0] or "py.test" in sys.argv[0])
    if len(sys.argv) > 1 and not is_pytest:
        for arg in sys.argv[1:]:
            try:
                path = Path(arg)
                if path.suffix not in (".py", ".md"):
                    continue
                try:
                    contents = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                if len(contents.splitlines()) < 50:
                    continue
                from agentflow.indexer.index_manager import update
                update(path, contents)
            except Exception as e:
                print(json.dumps({"hook": "write_indexer.py", "event": "index_update_error", "error": str(e), "path": str(path), "ts": time.time()}), file=sys.stderr)
        sys.exit(0)

    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        tool_input = data.get("tool_input", {})
        file_path = (
            tool_input.get("file_path")
            or tool_input.get("AbsolutePath")
            or tool_input.get("TargetFile")
        )
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
    except Exception as e:
        print(json.dumps({"hook": "write_indexer.py", "event": "index_update_stdin_error", "error": str(e), "ts": time.time()}), file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
