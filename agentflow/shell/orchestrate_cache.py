"""Orchestrate startup cache — pre-computes round state to save startup commands.

Generates .agentflow/orchestrate_cache.json from tasks.json + execution_plan.md
+ design_status.md + rate_calibration_claude.json. Regenerates only when source
file mtimes change, saving 4 bash commands + 1 IDX read on every orchestrate
startup.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _home_calibration() -> Path:
    """Return path to rate calibration file (home-relative)."""
    return Path.home() / ".agentflow" / "rate_calibration_claude.json"


def _source_paths(project_root: Path) -> dict[str, Path]:
    """Return mapping of logical name → absolute path for all tracked sources."""
    return {
        "tasks.json": project_root / "tasks.json",
        "execution_plan.md": project_root / "execution_plan.md",
        "design_status.md": project_root / "design_status.md",
        "state.json": project_root / ".agentflow" / "state.json",
        "rate_calibration_claude.json": _home_calibration(),
    }


def _cache_path(project_root: Path) -> Path:
    return project_root / ".agentflow" / "orchestrate_cache.json"


def _load_state(project_root: Path) -> dict:
    state_path = project_root / ".agentflow" / "state.json"
    if not state_path.exists():
        return {}
    try:
        with open(state_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _get_current_round(state_data: dict) -> str:
    return state_data.get("next_round", "unknown")


def _load_pending_tasks(project_root: Path, state_data: dict) -> tuple[list[dict], int]:
    """Return (slim_pending_list, all_pending_count).

    Slim list contains only {task_id, title, depends_on}.
    If state_data has task_ids_in_round, filter to that set; otherwise return all pending.
    """
    tasks_path = project_root / "tasks.json"
    try:
        with open(tasks_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return [], 0

    all_tasks: list[dict] = data.get("tasks", [])
    pending_all = [t for t in all_tasks if t.get("status") == "pending"]
    all_pending_count = len(pending_all)

    # Filter by round membership when available
    round_task_ids: set[str] | None = None
    if state_data and "task_ids_in_round" in state_data:
        round_task_ids = set(state_data["task_ids_in_round"])

    if round_task_ids:
        pending = [t for t in pending_all if t["task_id"] in round_task_ids]
    else:
        pending = pending_all

    slim = [
        {
            "task_id": t["task_id"],
            "title": t["title"],
            "depends_on": t.get("depends_on", []),
        }
        for t in pending
    ]
    return slim, all_pending_count


def _count_unresolved(project_root: Path) -> int:
    """Count UNRESOLVED rows in design_status.md.

    design_status.md format: | Item | Status | Decision |
    Status is field $3 in awk (1-indexed) / parts[2] in Python (0-indexed split by |).
    """
    design_path = project_root / "design_status.md"
    if not design_path.exists():
        return 0
    try:
        result = subprocess.run(
            [
                "awk",
                "-F|",
                '{gsub(/^[[:space:]]+|[[:space:]]+$/,"",$3); if($3=="UNRESOLVED")c++}END{print c+0}',
                str(design_path),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return int(result.stdout.strip() or "0")
    except (subprocess.TimeoutExpired, ValueError, OSError):
        # Python fallback
        count = 0
        try:
            with open(design_path) as f:
                for line in f:
                    parts = line.split("|")
                    if len(parts) >= 3 and parts[2].strip() == "UNRESOLVED":
                        count += 1
        except OSError:
            pass
        return count


def _load_calibration() -> dict:
    """Load EWMA fields from rate_calibration_claude.json, with defaults."""
    defaults = {"ewma_mean_tokens": 2500, "ewma_cv": 0.0, "sample_count": 0}
    cal_path = _home_calibration()
    if not cal_path.exists():
        return defaults
    try:
        with open(cal_path) as f:
            data = json.load(f)
        return {
            "ewma_mean_tokens": data.get("ewma_mean_tokens", defaults["ewma_mean_tokens"]),
            "ewma_cv": data.get("ewma_cv", defaults["ewma_cv"]),
            "sample_count": data.get("sample_count", defaults["sample_count"]),
        }
    except (json.JSONDecodeError, OSError):
        return defaults


def _collect_mtimes(project_root: Path) -> dict[str, float]:
    """Return mtime float for each source file that exists."""
    mtimes: dict[str, float] = {}
    for name, path in _source_paths(project_root).items():
        if path.exists():
            mtimes[name] = path.stat().st_mtime
    return mtimes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_cache(project_root: Path) -> Path:
    """Build and write .agentflow/orchestrate_cache.json.

    Reads tasks.json, execution_plan.md, design_status.md, .agentflow/state.json
    (optional), and ~/.agentflow/rate_calibration_claude.json. Idempotent: calling
    twice with unchanged sources produces identical output.

    Returns the cache file path.
    """
    project_root = Path(project_root)

    state_data = _load_state(project_root)
    current_round = _get_current_round(state_data)
    pending_tasks, all_pending_count = _load_pending_tasks(project_root, state_data)
    unresolved_design_count = _count_unresolved(project_root)
    cal = _load_calibration()
    source_mtimes = _collect_mtimes(project_root)

    cache = {
        "current_round": current_round,
        "pending_tasks": pending_tasks,
        "all_pending_count": all_pending_count,
        "unresolved_design_count": unresolved_design_count,
        "ewma_mean_tokens": cal["ewma_mean_tokens"],
        "ewma_cv": cal["ewma_cv"],
        "sample_count": cal["sample_count"],
        "source_mtimes": source_mtimes,
    }

    agentflow_dir = project_root / ".agentflow"
    agentflow_dir.mkdir(exist_ok=True)
    out = _cache_path(project_root)
    with open(out, "w") as f:
        json.dump(cache, f, indent=2)

    return out


def is_cache_stale(project_root: Path) -> bool:
    """Return True if .agentflow/orchestrate_cache.json is absent or any source is newer.

    Compares current mtime of each tracked source file against the mtime recorded
    in source_mtimes at cache-build time.
    """
    project_root = Path(project_root)
    out = _cache_path(project_root)

    if not out.exists():
        return True

    try:
        with open(out) as f:
            cache = json.load(f)
    except (json.JSONDecodeError, OSError):
        return True

    source_mtimes: dict[str, float] = cache.get("source_mtimes", {})
    if not source_mtimes:
        return True

    for name, path in _source_paths(project_root).items():
        if not path.exists():
            continue
        current_mtime = path.stat().st_mtime
        cached_mtime = source_mtimes.get(name, 0.0)
        if current_mtime > cached_mtime:
            return True

    return False
