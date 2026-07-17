import json
import os
import subprocess
import sys
import time
from pathlib import Path
from agentflow.tools.cleanup_violations import (
    flatten_archive,
    append_to_archive,
    auto_file_size_violations,
)
from agentflow.shell.session_paths import session_file

def _load_json(path: Path):
    with path.open() as f:
        return json.load(f)


def _log_event(project_root: Path, entry: dict) -> None:
    try:
        with open(project_root / ".agentflow" / "hook_drain_debug.jsonl", "a") as f:
            f.write(json.dumps({"source": "cleanup_tasks", "ts": time.time(), **entry}) + "\n")
    except Exception:
        pass


def _write_json(path: Path, data):
    with path.open("w") as f:
        json.dump(data, f, indent=2)
    print(f"  wrote {path}")


def _detect_merged_prs(project_root: Path, tasks_data: dict) -> bool:
    task_prs_path = project_root / ".agentflow" / "task_prs.json"
    agentflow_dir = project_root / ".agentflow"
    sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
    in_flight_path = session_file(agentflow_dir, "tasks_in_flight.json", sid)

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


def cleanup(project_root: Path) -> None:
    auto_file_size_violations(project_root)
    tasks_path = project_root / "tasks.json"
    archive_path = project_root / ".agentflow" / "tasks.archive.json"
    tasks_data = _load_json(tasks_path)
    _detect_merged_prs(project_root, tasks_data)
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
    completed_ids = [t["task_id"] for t in new_tasks if t.get("status") == "complete"]
    _log_event(project_root, {"event": "tasks_json_written", "trimmed": trimmed, "completed_ids": completed_ids})
    print(f"  trimmed {trimmed} completed task(s) to stubs")

    # --- tasks.archive.json: flatten nested batches ---
    if archive_path.exists():
        flat = flatten_archive(archive_path)
        _write_json(archive_path, flat)
        print(f"  flattened archive to {len(flat)} entries")

    # --- tasks_in_flight.json: remove completed tasks ---
    agentflow_dir = project_root / ".agentflow"
    sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
    in_flight_path = session_file(agentflow_dir, "tasks_in_flight.json", sid)
    if in_flight_path.exists():
        try:
            complete_ids = {t["task_id"] for t in new_tasks if t.get("status") == "complete"}
            with open(in_flight_path) as f:
                in_flight: list = json.load(f)
            still_pending = [tid for tid in in_flight if tid not in complete_ids]
            if len(still_pending) != len(in_flight):
                with open(in_flight_path, "w") as f:
                    json.dump(still_pending, f)
                _log_event(project_root, {"event": "tif_written", "still_in_flight": still_pending})
                print(f"  removed {len(in_flight) - len(still_pending)} completed task(s) from tasks_in_flight")
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    try:
        cr_path = project_root / ".agentflow" / "current_round.json"
        if cr_path.exists():
            cr_data = json.loads(cr_path.read_text())
            rtasks = set(cr_data.get("task_ids", []))
            if rtasks and rtasks.issubset({t["task_id"] for t in new_tasks if t.get("status") in ("complete", "MERGED")}):
                cr_path.unlink(missing_ok=True)
    except (OSError, ValueError, json.JSONDecodeError):
        pass



if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    print(f"Cleaning up tasks in: {root}")
    cleanup(root)
    print("Done.")
