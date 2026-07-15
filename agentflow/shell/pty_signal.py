import sys
import os
import json
import fcntl
from pathlib import Path
import tempfile
import contextlib
from agentflow.shell.session_paths import session_file

def find_workspace_root() -> Path:
    p = Path.cwd().resolve()
    for parent in [p] + list(p.parents):
        if (parent / "tasks.json").exists() or (parent / ".agentflow").exists():
            return parent
    return p

@contextlib.contextmanager
def file_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    f = open(lock_path, "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield f
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()

def _write_atomic(file_path: Path, data: any):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=str(file_path.parent), prefix=file_path.name + ".")
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, file_path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

def task_start(task_id: str, workspace_root: Path = None):
    if not workspace_root:
        workspace_root = find_workspace_root()
    agentflow_dir = workspace_root / ".agentflow"
    sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
    in_flight_file = session_file(agentflow_dir, "tasks_in_flight.json", sid)
    lock_path = agentflow_dir / "tasks_in_flight.lock"

    tasks_file = workspace_root / "tasks.json"
    valid_task_ids = set()
    if tasks_file.exists():
        try:
            with open(tasks_file, "r") as f:
                tasks_data = json.load(f)
                for t in tasks_data.get("tasks", []):
                    if isinstance(t, dict) and "task_id" in t:
                        valid_task_ids.add(t["task_id"])
        except Exception as e:
            print(f"Warning: failed to read tasks.json: {e}", file=sys.stderr)

    with file_lock(lock_path):
        in_flight_set = set()
        if in_flight_file.exists():
            try:
                with open(in_flight_file, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for tid in data:
                            if not valid_task_ids or tid in valid_task_ids:
                                in_flight_set.add(tid)
            except Exception as e:
                print(f"Warning: failed to read tasks_in_flight.json: {e}", file=sys.stderr)

        in_flight_set.add(task_id)
        _write_atomic(in_flight_file, sorted(list(in_flight_set)))

def task_done(task_id: str, workspace_root: Path = None, sid: str = ""):
    if not workspace_root:
        workspace_root = find_workspace_root()
    if not sid:
        sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
    agentflow_dir = workspace_root / ".agentflow"
    in_flight_file = session_file(agentflow_dir, "tasks_in_flight.json", sid)
    complete_file = session_file(agentflow_dir, "task_complete.json", sid)
    lock_path = agentflow_dir / "tasks_in_flight.lock"

    with file_lock(lock_path):
        in_flight_set = set()
        if in_flight_file.exists():
            try:
                with open(in_flight_file, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        in_flight_set = set(data)
            except Exception as e:
                print(f"Warning: failed to read tasks_in_flight.json: {e}", file=sys.stderr)

        if task_id in in_flight_set:
            in_flight_set.remove(task_id)

        if not in_flight_set:
            _write_atomic(complete_file, {"status": "complete"})
            _write_atomic(in_flight_file, [])  # tombstone: [] = drained; absent = never initialized
        else:
            _write_atomic(in_flight_file, sorted(list(in_flight_set)))

def handoff_complete(workspace_root: Path = None):
    if not workspace_root:
        workspace_root = find_workspace_root()
    agentflow_dir = workspace_root / ".agentflow"
    handoff_file = agentflow_dir / "handoff_complete.json"
    _write_atomic(handoff_file, {"status": "complete"})

def main():
    args = sys.argv[1:]
    if not args:
        print("Error: subcommand required (task_start, task_done, handoff_complete)", file=sys.stderr)
        sys.exit(1)

    subcommand = args[0]
    if subcommand in ("task_start", "task_done"):
        if len(args) < 2:
            print(f"Error: task_id required for {subcommand}", file=sys.stderr)
            sys.exit(1)
        task_id = args[1]
        try:
            if subcommand == "task_start":
                task_start(task_id)
            else:
                task_done(task_id)
        except Exception as e:
            print(f"Error executing {subcommand}: {e}", file=sys.stderr)
            sys.exit(1)
    elif subcommand == "handoff_complete":
        try:
            handoff_complete()
        except Exception as e:
            print(f"Error executing handoff_complete: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Error: unknown subcommand '{subcommand}'", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
