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


def auto_file_size_violations(project_root: Path) -> None:
    violations_path = project_root / ".agentflow" / "size_violations.jsonl"
    if not violations_path.exists():
        return

    tasks_path = project_root / "tasks.json"
    if not tasks_path.exists():
        return

    try:
        tasks_data = _load_json(tasks_path)
    except Exception:
        return

    archive_path = project_root / ".agentflow" / "tasks.archive.json"
    archive_tasks = []
    if archive_path.exists():
        try:
            archive_tasks = flatten_archive(archive_path)
        except Exception:
            pass

    all_tasks = tasks_data.get("tasks", []) + archive_tasks

    import re
    max_id = 0
    id_pattern = re.compile(r"^T-(\d+)$")
    for t in all_tasks:
        tid = t.get("task_id", "")
        m = id_pattern.match(tid)
        if m:
            max_id = max(max_id, int(m.group(1)))

    violations = []
    try:
        with violations_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    violations.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        return

    new_tasks = []
    for v in violations:
        filename = v.get("file")
        limit = v.get("limit")
        ts = v.get("ts")
        if not filename or not limit or not ts:
            continue

        file_path = project_root / filename
        if not file_path.exists():
            continue

        try:
            current_lines = len(file_path.read_text(encoding="utf-8").splitlines())
        except Exception:
            continue

        if current_lines <= limit:
            continue

        # Check if already filed
        already_filed = False
        for t in all_tasks + new_tasks:
            if t.get("status") == "pending" and filename in t.get("owns", []):
                already_filed = True
                break
            desc = t.get("description", "")
            if filename in desc and ts in desc:
                already_filed = True
                break

        if already_filed:
            continue

        max_id += 1
        new_task_id = f"T-{max_id:03d}"
        new_task = {
            "task_id": new_task_id,
            "title": f"Split {filename} — size violation",
            "description": f"Split {filename} to resolve size violation of {current_lines} lines (limit: {limit}). Violation timestamp: {ts}.",
            "owns": [filename],
            "reads": [],
            "depends_on": [],
            "status": "pending"
        }
        new_tasks.append(new_task)

    if new_tasks:
        tasks_data["tasks"].extend(new_tasks)
        _write_json(tasks_path, tasks_data)
        print(f"  auto-filed {len(new_tasks)} size violation split task(s)")


def cleanup(project_root: Path) -> None:
    auto_file_size_violations(project_root)

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
