#!/usr/bin/env python3
"""PostToolUse hook: block Write/Edit when file exceeds line limit."""

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

    try:
        file_path = data.get("tool_input", {}).get("file_path")
        if not file_path:
            sys.exit(0)

        path = Path(file_path).resolve()
        cwd = Path.cwd().resolve()

        try:
            rel_path = path.relative_to(cwd)
            parts = rel_path.parts
            rel_path_str = str(rel_path)
        except ValueError:
            parts = path.parts
            rel_path_str = str(path)

        is_py = path.suffix == ".py"
        is_commands = "commands" in parts
        is_tests = "tests" in parts

        if not is_py and not is_commands:
            sys.exit(0)

        if is_commands:
            limit = 150
        elif is_tests and is_py:
            limit = 350
        elif is_py:
            limit = 250
        else:
            sys.exit(0)

        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            sys.exit(0)

        lines = content.splitlines()
        n_lines = len(lines)
        if n_lines == 0:
            sys.exit(0)

        # Check if file is a stub (more than 50% pass or ellipsis lines)
        pass_lines = sum(1 for line in lines if line.strip() in ("pass", "..."))
        if pass_lines > 0.5 * n_lines:
            sys.exit(0)

        if n_lines > limit:
            print(
                f"FILE TOO LARGE: {rel_path_str} is {n_lines} lines (limit {limit}) — "
                "split by responsibility boundary before proceeding.",
                file=sys.stderr,
            )
            try:
                violations_path = Path(os.getcwd()) / ".agentflow" / "size_violations.jsonl"
                violations_path.parent.mkdir(parents=True, exist_ok=True)
                entry = {
                    "file": rel_path_str,
                    "blocked_lines": n_lines,
                    "actual_lines": n_lines,
                    "limit": limit,
                    "ts": datetime.now().isoformat(),
                }
                with violations_path.open("a", encoding="utf-8") as _f:
                    _f.write(json.dumps(entry) + "\n")
            except Exception:
                pass
            sys.exit(1)

    except Exception:
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
