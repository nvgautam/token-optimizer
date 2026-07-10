"""Per-task token estimator built from task_token_log.jsonl."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LOG_PATH = Path.home() / ".agentflow" / "task_token_log.jsonl"
DEFAULT_OUTPUT_PATH = Path.home() / ".agentflow" / "task_estimator.json"

STATIC_DEFAULT = 2500
MIN_SAMPLES = 7
HIGH_CV_THRESHOLD = 0.5


def aggregate_tokens(records: list[dict]) -> dict[str, int]:
    """Sum abs(token_delta) per task_id across all records.

    Records with missing or None task_id/token_delta are silently skipped.
    """
    totals: dict[str, int] = {}
    for record in records:
        task_id = record.get("task_id")
        raw_delta = record.get("token_delta")
        if task_id is None or raw_delta is None:
            continue
        delta = abs(int(raw_delta))
        totals[task_id] = totals.get(task_id, 0) + delta
    return totals


def _percentile(values: list[float], pct: float) -> float:
    """85th-percentile via linear interpolation (no external deps)."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 1:
        return float(sorted_vals[0])
    idx = (pct / 100.0) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    return sorted_vals[lo] + (idx - lo) * (sorted_vals[hi] - sorted_vals[lo])


def compute_stats(per_task_totals: dict[str, int]) -> dict:
    """Return mean, p85, cv, sample_count from per-task token totals."""
    values = list(per_task_totals.values())
    n = len(values)
    if n == 0:
        return {"mean": 0.0, "p85": 0.0, "cv": 0.0, "sample_count": 0}
    mean = float(statistics.mean(values))
    p85 = _percentile(values, 85.0)
    stdev = float(statistics.stdev(values)) if n > 1 else 0.0
    cv = stdev / mean if mean > 0 else 0.0
    return {"mean": mean, "p85": p85, "cv": cv, "sample_count": n}


def compute(
    log_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> dict:
    """Load log, aggregate per-task, write task_estimator.json, return stats."""
    log_path = Path(log_path) if log_path is not None else DEFAULT_LOG_PATH
    output_path = Path(output_path) if output_path is not None else DEFAULT_OUTPUT_PATH

    records: list[dict] = []
    if log_path.exists():
        with open(log_path, encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    records.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue  # skip malformed lines silently

    per_task = aggregate_tokens(records)
    stats = compute_stats(per_task)
    stats["timestamp"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(stats, fh)

    return stats


def estimate(
    estimated_lines: int,
    file_count: int,
    stats_path: str | Path | None = None,
) -> int:
    """Return predicted token cost using stored stats.

    Branching logic:
      sample_count < 7          → 2500 (static default)
      sample_count >= 7, cv < 0.5  → int(mean)
      sample_count >= 7, cv >= 0.5 → int(p85)
    """
    stats_path = Path(stats_path) if stats_path is not None else DEFAULT_OUTPUT_PATH

    if not stats_path.exists():
        return STATIC_DEFAULT

    with open(stats_path, encoding="utf-8") as fh:
        stats = json.load(fh)

    sample_count = int(stats.get("sample_count", 0))
    if sample_count < MIN_SAMPLES:
        return STATIC_DEFAULT

    cv = float(stats.get("cv", 0.0))
    if cv < HIGH_CV_THRESHOLD:
        mean = stats.get("mean")
        return int(mean) if mean is not None else STATIC_DEFAULT
    p85 = stats.get("p85")
    return int(p85) if p85 is not None else STATIC_DEFAULT
