import json
import math
import statistics
from pathlib import Path
from typing import Optional

_TERMINAL_LABELS = frozenset({"pre_restart", "session_end"})

def calibrate_capacity(project_root: Path, current_start_pct: float, agent: str = "claude") -> dict:
    """
    Calibrates capacity using a percentage-based model.
    """
    cal_dir = Path.home() / ".agentflow"
    cal_file = cal_dir / f"rate_calibration_{agent}.json"
    
    cal_data = {}
    ewma_pct_per_task = 10.0
    ewma_alpha = 0.3
    
    if cal_file.exists():
        try:
            with open(cal_file, "r") as f:
                cal_data = json.load(f)
            if isinstance(cal_data, dict):
                ewma_pct_per_task = cal_data.get("ewma_pct_per_task", 10.0)
                ewma_alpha = cal_data.get("ewma_alpha", 0.3)
            else:
                cal_data = {}
        except Exception:
            cal_data = {}
            
    ledger_path = project_root / "agentflow_ledger.json"
    sessions = []
    usage_snapshots = []
    if ledger_path.exists():
        try:
            with open(ledger_path, "r") as f:
                ledger = json.load(f)
            sessions = ledger.get("sessions", [])
            usage_snapshots = ledger.get("usage_snapshots", [])
        except Exception:
            pass

    ewma = ewma_pct_per_task
    
    for s in sessions:
        if s.get("status") == "closed" and s.get("agent") == agent:
            start_pct = s.get("start_pct_5hr")
            if start_pct is None:
                start_pct = s.get("start_pct")
            end_pct = s.get("end_pct_5hr")
            if end_pct is None:
                end_pct = s.get("end_pct")
                
            if start_pct is not None and end_pct is not None:
                try:
                    start_val = float(start_pct)
                    end_val = float(end_pct)
                except (TypeError, ValueError):
                    continue
                    
                pct_consumed = end_val - start_val
                if end_val < start_val:
                    pct_consumed = (100.0 - start_val) + end_val
                    
                task_ids = s.get("task_ids")
                if isinstance(task_ids, str) and task_ids.strip():
                    parts = [t.strip() for t in task_ids.split(",") if t.strip()]
                    num_tasks = len(parts) if parts else 1
                else:
                    num_tasks = 1
                    
                pct_per_task = pct_consumed / num_tasks
                ewma = ewma_alpha * pct_per_task + (1 - ewma_alpha) * ewma

    current_pct_remaining = 100.0 - current_start_pct
    if ewma > 0:
        tasks_remaining = math.floor(current_pct_remaining / ewma)
    else:
        tasks_remaining = 0
    tasks_remaining = max(0, tasks_remaining)
    
    # Compute ewma_cv from usage_snapshots (T-164)
    snapshot_pct_values: list[float] = []
    pending_start: dict | None = None
    for snap in usage_snapshots:
        label = snap.get("label")
        if label == "session_start":
            pending_start = snap
        elif label == "session_end" and pending_start is not None:
            try:
                start_val = float(pending_start.get("start_pct_5hr", 0))
                end_val = float(snap.get("start_pct_5hr", 0))
                pct_consumed = end_val - start_val
                if end_val < start_val:
                    pct_consumed = (100.0 - start_val) + end_val
                snapshot_pct_values.append(pct_consumed)
            except (TypeError, ValueError):
                pass
            pending_start = None

    if len(snapshot_pct_values) >= 2:
        mean_val = statistics.mean(snapshot_pct_values)
        ewma_cv = statistics.stdev(snapshot_pct_values) / mean_val if mean_val > 0 else 0.0
    else:
        ewma_cv = 0.0

    cal_data["ewma_pct_per_task"] = ewma
    cal_data["tasks_remaining"] = tasks_remaining
    cal_data["ewma_alpha"] = ewma_alpha
    cal_data["ewma_cv"] = ewma_cv
    cal_data["sample_count"] = len(snapshot_pct_values)
    
    try:
        cal_dir.mkdir(parents=True, exist_ok=True)
        with open(cal_file, "w") as f:
            json.dump(cal_data, f, indent=2)
    except Exception:
        pass

    return cal_data


def get_baseline_usage_from_ledger(
    project_root: Path,
    session_type: Optional[str] = None,
) -> Optional[dict]:
    """Retrieve the most recent terminal usage snapshot from agentflow_ledger.json.

    Queries pre_restart or session_end snapshots from the ledger, optionally
    filtered by session_type, as a non-disruptive alternative to PTY /usage
    injection at session start.

    Parameters
    ----------
    project_root:
        Root directory that contains agentflow_ledger.json.
    session_type:
        When provided, prefer snapshots whose ``session_type`` field matches.
        Falls back to the most recent terminal snapshot if no typed match exists.

    Returns
    -------
    A usage snapshot dict (containing at minimum ``start_pct_5hr`` and ``label``)
    or ``None`` if the ledger is absent, malformed, or has no terminal snapshots.
    """
    ledger_path = project_root / "agentflow_ledger.json"
    if not ledger_path.exists():
        return None
    try:
        with open(ledger_path, encoding="utf-8") as fh:
            ledger = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None

    snapshots = ledger.get("usage_snapshots", [])
    terminal = [s for s in snapshots if s.get("label") in _TERMINAL_LABELS]

    if session_type:
        typed = [s for s in terminal if s.get("session_type") == session_type]
        if typed:
            return typed[-1]

    return terminal[-1] if terminal else None
