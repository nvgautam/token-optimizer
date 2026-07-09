"""Shadow analyzer for headroom A/B testing.

Records output token deltas between headroom on/off arms to measure
compression savings via output token reduction.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

AB_LOG_FILENAME = "headroom_ab_log.jsonl"


def _ab_log_path(project_root: Path) -> Path:
    """Return the path to the headroom A/B log file."""
    return project_root / ".agentflow" / AB_LOG_FILENAME


def record_output(
    project_root: Path | str,
    arm: str,
    output_tokens: int,
    ts: str | None = None,
) -> None:
    """Append {ts, arm, output_tokens} to headroom_ab_log.jsonl.

    Args:
        project_root: Root of the project
        arm: "on" or "off"
        output_tokens: Number of output tokens for this record
        ts: Optional timestamp; defaults to now()
    """
    log_path = _ab_log_path(Path(project_root))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "ts": ts if ts is not None else datetime.now().isoformat(),
        "arm": arm,
        "output_tokens": output_tokens,
    }
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def compute_delta(project_root: Path | str) -> dict:
    """Load log, compute per-arm stats and delta.

    Returns:
        {
            "on": {"mean": float, "n": int},
            "off": {"mean": float, "n": int},
            "delta": float | None  # mean_on - mean_off, or None if either arm missing
        }
    """
    log_path = _ab_log_path(Path(project_root))

    on_values = []
    off_values = []

    if log_path.exists():
        for line in log_path.read_text().strip().split("\n"):
            if not line:
                continue
            entry = json.loads(line)
            arm = entry.get("arm")
            output_tokens = entry.get("output_tokens", 0)
            if arm == "on":
                on_values.append(output_tokens)
            elif arm == "off":
                off_values.append(output_tokens)

    on_mean = sum(on_values) / len(on_values) if on_values else 0.0
    off_mean = sum(off_values) / len(off_values) if off_values else 0.0

    # delta is None if either arm is empty
    delta = None
    if on_values and off_values:
        delta = on_mean - off_mean

    return {
        "on": {"mean": on_mean, "n": len(on_values)},
        "off": {"mean": off_mean, "n": len(off_values)},
        "delta": delta,
    }
