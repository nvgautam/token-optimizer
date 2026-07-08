#!/usr/bin/env python3
"""PostToolUse hook (Agent tool): call pty_signal.py task_done for any in-flight
task that has been marked complete in tasks.json.

Fires after every Agent tool return. Eliminates reliance on LLM compliance
for emitting AGENTFLOW_TASK_COMPLETE signals.
"""

import json
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
    # Consume stdin (required by hook protocol) but we don't need the content.
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    root = _find_workspace_root()
    agentflow_dir = root / ".agentflow"
    in_flight_file = agentflow_dir / "tasks_in_flight.json"

    if not in_flight_file.exists():
        sys.exit(0)

    try:
        with open(in_flight_file) as f:
            in_flight: list[str] = json.load(f)
    except Exception:
        sys.exit(0)

    if not in_flight:
        sys.exit(0)

    tasks_file = root / "tasks.json"
    if not tasks_file.exists():
        sys.exit(0)

    try:
        with open(tasks_file) as f:
            tasks_data = json.load(f)
    except Exception:
        sys.exit(0)

    status_by_id = {t["task_id"]: t.get("status", "pending") for t in tasks_data.get("tasks", [])}

    signal_script = root / "agentflow" / "shell" / "pty_signal.py"

    completed = []
    for task_id in in_flight:
        if status_by_id.get(task_id, "pending") != "pending":
            completed.append(task_id)
            try:
                subprocess.run(
                    [sys.executable, str(signal_script), "task_done", task_id],
                    check=False,
                    capture_output=True,
                )
            except Exception:
                pass

    if completed:
        still_pending = [tid for tid in in_flight if tid not in set(completed)]
        try:
            with open(in_flight_file, "w") as f:
                json.dump(still_pending, f)
        except Exception:
            pass

    sys.exit(0)


if __name__ == "__main__":
    main()
