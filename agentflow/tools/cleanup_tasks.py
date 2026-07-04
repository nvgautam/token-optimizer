"""
Enforce tasks.json / tasks.archive.json invariants after merge.

- tasks.json: completed tasks trimmed to {"task_id": ..., "status": "complete"}
- tasks.archive.json: flat list of full task definitions (no nested batches)
"""
import json
import sys
from pathlib import Path


def _load_json(path: Path):
    with path.open() as f:
        return json.load(f)


def _write_json(path: Path, data):
    with path.open("w") as f:
        json.dump(data, f, indent=2)
    print(f"  wrote {path}")


def flatten_archive(archive_path: Path) -> list:
    """Return flat list of task dicts from potentially nested-batch archive."""
    raw = _load_json(archive_path)
    flat = []
    for item in raw:
        if isinstance(item, list):
            flat.extend(item)
        elif isinstance(item, dict):
            flat.append(item)
    return flat


def cleanup(project_root: Path) -> None:
    tasks_path = project_root / "tasks.json"
    archive_path = project_root / ".agentflow" / "tasks.archive.json"

    # --- tasks.json: trim completed tasks to stubs ---
    tasks_data = _load_json(tasks_path)
    tasks = tasks_data["tasks"]

    archived_ids = set()
    if archive_path.exists():
        for entry in flatten_archive(archive_path):
            tid = entry.get("task_id")
            if tid:
                archived_ids.add(tid)

    trimmed = 0
    new_tasks = []
    for t in tasks:
        if t.get("status") == "complete" and len(t) > 2:
            # Archive if not already there
            if t.get("task_id") not in archived_ids:
                archived_ids.add(t["task_id"])
                append_to_archive(archive_path, t)
            new_tasks.append({"task_id": t["task_id"], "status": "complete"})
            trimmed += 1
        else:
            new_tasks.append(t)

    tasks_data["tasks"] = new_tasks
    _write_json(tasks_path, tasks_data)
    print(f"  trimmed {trimmed} completed task(s) to stubs")

    # --- tasks.archive.json: flatten nested batches ---
    if archive_path.exists():
        flat = flatten_archive(archive_path)
        _write_json(archive_path, flat)
        print(f"  flattened archive to {len(flat)} entries")


def append_to_archive(archive_path: Path, task: dict) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if archive_path.exists():
        existing = flatten_archive(archive_path)
    existing.append(task)
    with archive_path.open("w") as f:
        json.dump(existing, f, indent=2)


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    print(f"Cleaning up tasks in: {root}")
    cleanup(root)
    print("Done.")
