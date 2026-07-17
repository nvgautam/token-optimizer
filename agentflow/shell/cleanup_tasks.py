"""Cleanup tasks wrapper.

Performs tasks.json cleanup and writes the task_complete.json file atomically.
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
from pathlib import Path
from agentflow.tools.cleanup_tasks import cleanup
from agentflow.shell.session_paths import session_file

def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    print(f"Cleaning up tasks in: {root}")
    
    # Run the existing cleanup tool
    cleanup(root)
    
    # Write the task_complete.json signal atomically
    agentflow_dir = root / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)
    sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
    signal_path = session_file(agentflow_dir, "task_complete.json", sid)
    
    temp_fd, temp_path = tempfile.mkstemp(dir=str(signal_path.parent), prefix="task_complete_", suffix=".tmp")
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            json.dump({"status": "complete"}, f)
        os.replace(temp_path, signal_path)
    except Exception as e:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise e
    print("Atomic task_complete.json written.")
    try:
        with open(agentflow_dir / "hook_drain_debug.jsonl", "a") as _lf:
            import time as _t
            _lf.write(json.dumps({"event": "task_complete_written", "status": "complete", "ts": _t.time()}) + "\n")
    except Exception:
        pass

if __name__ == "__main__":
    main()
