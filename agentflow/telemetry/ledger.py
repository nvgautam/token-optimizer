import json
import fcntl
from pathlib import Path
from contextlib import contextmanager

LEDGER_FILE = Path(__file__).parent.parent.parent / "agentflow_ledger.json"
_ledger_override = None

def set_ledger_override(path: str | None):
    global _ledger_override
    _ledger_override = path

def get_ledger_override() -> str | None:
    return _ledger_override

def _active_ledger_path() -> Path:
    return Path(_ledger_override) if _ledger_override else LEDGER_FILE

@contextmanager
def ledger_lock():
    lock = Path(str(_active_ledger_path()) + ".lock")
    with open(lock, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)

def load_ledger() -> dict:
    path = _active_ledger_path()
    if not path.exists():
        return {"sessions": [], "shadow_state": {"accumulated_context": 0, "compaction_events": 0}}
    with open(path) as f:
        return json.load(f)

def save_ledger(ledger: dict):
    path = _active_ledger_path()
    with open(path, "w") as f:
        json.dump(ledger, f, indent=2)

def active_session(ledger: dict) -> dict | None:
    for s in reversed(ledger["sessions"]):
        if s.get("status") == "open":
            return s
    return None

# Keep compatibility with existing stubs if any imports exist
def read_ledger(path: Path) -> dict:
    if not path.exists():
        return {"sessions": [], "shadow_state": {"accumulated_context": 0, "compaction_events": 0}}
    with open(path) as f:
        return json.load(f)

def write_ledger(path: Path, data: dict) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def session_total(path: Path, task_id: str) -> int:
    ledger = read_ledger(path)
    for s in reversed(ledger.get("sessions", [])):
        if s.get("task_ids") == task_id or task_id in s.get("task_ids", "").split(","):
            return s.get("input_tokens", 0) + s.get("output_tokens", 0)
    return 0

def project_total(path: Path) -> int:
    ledger = read_ledger(path)
    total = 0
    for s in ledger.get("sessions", []):
        total += s.get("input_tokens", 0) + s.get("output_tokens", 0)
    return total
