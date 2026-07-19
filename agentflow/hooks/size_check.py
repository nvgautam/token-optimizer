#!/usr/bin/env python3
"""PostToolUse hook: block Write/Edit when file exceeds line limit."""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path


def is_task_filed(file_path: Path, cwd: Path) -> bool:
    try:
        rel_path = file_path.relative_to(cwd)
        rel_path_str = str(rel_path)
    except ValueError:
        rel_path_str = str(file_path)
    filename = file_path.name

    # 1. Check tasks.json
    tasks_file = cwd / "tasks.json"
    if tasks_file.exists():
        try:
            data = json.loads(tasks_file.read_text(encoding="utf-8"))
            for task in data.get("tasks", []):
                # Check owns
                owns = task.get("owns", [])
                if isinstance(owns, list):
                    if any(rel_path_str in str(o) or filename in str(o) for o in owns):
                        return True
                # Check description/title/goals
                for key in ("title", "description", "goals", "goal"):
                    val = task.get(key)
                    if val and (rel_path_str in str(val) or filename in str(val)):
                        return True
        except Exception:
            pass

    # 2. Check .agentflow/tasks.archive.json
    archive_file = cwd / ".agentflow" / "tasks.archive.json"
    if archive_file.exists():
        try:
            data = json.loads(archive_file.read_text(encoding="utf-8"))
            tasks_list = data if isinstance(data, list) else data.get("tasks", [])
            for task in tasks_list:
                owns = task.get("owns", [])
                if isinstance(owns, list):
                    if any(rel_path_str in str(o) or filename in str(o) for o in owns):
                        return True
                for key in ("title", "description", "goals", "goal"):
                    val = task.get(key)
                    if val and (rel_path_str in str(val) or filename in str(val)):
                        return True
        except Exception:
            pass

    # 3. Check execution_plan.md
    plan_file = cwd / "execution_plan.md"
    if plan_file.exists():
        try:
            content = plan_file.read_text(encoding="utf-8")
            if rel_path_str in content or filename in content:
                return True
        except Exception:
            pass

    return False


def main() -> None:
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

        path = Path(file_path).resolve()
        cwd = Path(os.getcwd()).resolve()

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
        else:
            limit = 250

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
            if not is_task_filed(path, cwd):
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
                except Exception as e:
                    print(json.dumps({"hook": "size_check.py", "event": "violations_write_error", "error": str(e), "ts": time.time()}), file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(json.dumps({"hook": "size_check.py", "event": "size_check_error", "error": str(e), "ts": time.time()}), file=sys.stderr)
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
