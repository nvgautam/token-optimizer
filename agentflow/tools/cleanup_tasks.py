import json
import subprocess
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
    raw = _load_json(archive_path)
    flat = []
    for item in raw:
        if isinstance(item, list):
            flat.extend(item)
        elif isinstance(item, dict):
            flat.append(item)
    return flat


def _detect_merged_prs(project_root: Path, tasks_data: dict) -> bool:
    task_prs_path = project_root / ".agentflow" / "task_prs.json"
    in_flight_path = project_root / ".agentflow" / "tasks_in_flight.json"

    if not task_prs_path.exists():
        return False

    try:
        task_prs: dict = json.loads(task_prs_path.read_text("utf-8"))
        if not in_flight_path.exists():
            return False
        in_flight: list = json.loads(in_flight_path.read_text("utf-8"))
    except Exception:
        return False

    if not in_flight:
        return False

    tasks_by_id = {t["task_id"]: t for t in tasks_data.get("tasks", [])}

    marked_any = False
    for task_id in in_flight:
        pr_url = task_prs.get(task_id)
        if not pr_url:
            continue
        task = tasks_by_id.get(task_id)
        if task is None:
            continue
        if task.get("status") == "complete":
            continue  # idempotent: skip already-complete tasks
        try:
            result = subprocess.run(
                ["gh", "pr", "view", pr_url, "--json", "state", "--jq", ".state"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip() == "MERGED":
                task["status"] = "complete"
                marked_any = True
        except (OSError, subprocess.TimeoutExpired, Exception):
            continue  # skip this task, continue with others

    return marked_any


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
            "title": f"Split {filename} — size violation",
            "description": _split_description(filename, current_lines, limit, ts),
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

    # Detect newly-merged PRs before trimming so they get archived in this run
    merged_any = _detect_merged_prs(project_root, tasks_data)

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

    # --- tasks_in_flight.json: remove completed tasks ---
    in_flight_path = project_root / ".agentflow" / "tasks_in_flight.json"
    if in_flight_path.exists():
        try:
            complete_ids = {t["task_id"] for t in new_tasks if t.get("status") == "complete"}
            with open(in_flight_path) as f:
                in_flight: list = json.load(f)
            still_pending = [tid for tid in in_flight if tid not in complete_ids]
            if len(still_pending) != len(in_flight):
                with open(in_flight_path, "w") as f:
                    json.dump(still_pending, f)
                print(f"  removed {len(in_flight) - len(still_pending)} completed task(s) from tasks_in_flight")
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    # --- current_round.json: delete after merge ---
    if merged_any:
        current_round_path = project_root / ".agentflow" / "current_round.json"
        current_round_path.unlink(missing_ok=True)


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
