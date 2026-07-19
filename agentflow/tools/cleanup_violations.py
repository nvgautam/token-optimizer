import json
import re
from pathlib import Path


def _load_json(path: Path):
    with path.open() as f:
        return json.load(f)


def _write_json(path: Path, data):
    with path.open("w") as f:
        json.dump(data, f, indent=2)
    print(f"  wrote {path}")


def flatten_archive(archive_path: Path) -> list:
    raw = _load_json(archive_path)
    flat = []
    for item in raw:
        if isinstance(item, list):
            flat.extend(item)
        elif isinstance(item, dict):
            flat.append(item)
    return flat


def append_to_archive(archive_path: Path, task: dict) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if archive_path.exists():
        existing = flatten_archive(archive_path)
    existing.append(task)
    with archive_path.open("w") as f:
        json.dump(existing, f, indent=2)


def _split_description(filename: str, current_lines: int, limit: int, ts: str) -> str:
    parts = filename.replace("\\", "/").split("/")
    base = f"Split {filename} ({current_lines} lines, limit {limit}). Violation timestamp: {ts}."
    if "commands" in parts:
        return base + " Choose the split boundary by phase/section responsibility, not line count. Extract a cohesive section into a sub-file; replace with 'Lazy load: Read <subfile>.md now.' Verify each output file is ≤ 150 lines after splitting."
    if "tests" in parts:
        return base + " Choose the split boundary by test class or fixture group, not line count. Verify each output file is ≤ 350 lines after splitting."
    return base + " Read the file first, identify distinct responsibilities, then choose the split boundary by domain. Verify each output file is ≤ 250 lines after splitting."


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
    try:
        archive_tasks = flatten_archive(archive_path) if archive_path.exists() else []
    except Exception:
        archive_tasks = []
    all_tasks = tasks_data.get("tasks", []) + archive_tasks

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

        already_filed = any(
            (t.get("status") == "pending" and filename in t.get("owns", []))
            or (filename in t.get("description", "") and ts in t.get("description", ""))
            for t in all_tasks + new_tasks
        )
        if already_filed:
            continue

        max_id += 1
        new_task_id = f"T-{max_id:03d}"
        new_task = {
            "task_id": new_task_id,
            "status": "pending"
        }
        new_tasks.append(new_task)

        # Append addendum to execution_plan.md under lock
        title = f"Split {filename} — size violation"
        goal = _split_description(filename, current_lines, limit, ts)
        owns = [filename]
        addendum = f"\n## Addendum: {new_task_id} — {title}\n\n**Goal:** {goal}\n\n**Owns:** {json.dumps(owns)}\n"

        ep_path = project_root / "execution_plan.md"
        lock_path = project_root / ".agentflow" / "execution_plan.md.lock"
        import fcntl
        import tempfile
        import os
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with open(lock_path, "a+", encoding="utf-8") as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                if ep_path.exists():
                    content = ep_path.read_text("utf-8")
                    if not content.endswith("\n"):
                        content += "\n"
                    content += addendum

                    # Atomic write
                    fd, tmp = tempfile.mkstemp(dir=str(ep_path.parent))
                    try:
                        with os.fdopen(fd, "w", encoding="utf-8") as f:
                            f.write(content)
                        os.replace(tmp, str(ep_path))
                    except Exception:
                        try: os.unlink(tmp)
                        except OSError: pass
                        raise
        except Exception as e:
            print(f"Error appending addendum for {new_task_id}: {e}")

    if new_tasks:
        tasks_data["tasks"].extend(new_tasks)
        _write_json(tasks_path, tasks_data)
        print(f"  auto-filed {len(new_tasks)} size violation split task(s)")
