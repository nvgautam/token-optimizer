"""Shadow analyzer for headroom A/B testing.

Records compression-side token counts for headroom on/off arms to measure
savings via tokens_before delta between arms.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

AB_LOG_FILENAME = "headroom_ab_log.jsonl"


def _ab_log_path(project_root: Path) -> Path:
    """Return the path to the headroom A/B log file."""
    return project_root / ".agentflow" / AB_LOG_FILENAME


def record_compression(
    project_root: Path | str,
    arm: str,
    tokens_before: int,
    tokens_after: int,
    ts: str | None = None,
) -> None:
    """Append {ts, arm, tokens_before, tokens_after} to headroom_ab_log.jsonl.

    Called from _compress_payload() after the compress decision so each call
    is logged regardless of whether the arm ran or skipped compression.

    Args:
        project_root: Root of the project (used to locate .agentflow/)
        arm: "on" or "off"
        tokens_before: Token count before compression (0 when arm="off")
        tokens_after: Token count after compression (0 when arm="off")
        ts: Optional timestamp; defaults to now()
    """
    log_path = _ab_log_path(Path(project_root))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "ts": ts if ts is not None else datetime.now().isoformat(),
        "arm": arm,
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
    }
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def compute_delta(project_root: Path | str) -> dict:
    """Load log, compute per-arm stats on tokens_before and return delta.

    tokens_before is the proxy for savings: when arm="on" headroom ran and
    compressed; when arm="off" it was skipped (tokens_before=0). The delta
    between arms' mean tokens_before reflects the compression headroom applied.

    Returns:
        {
            "on": {"mean": float, "n": int},
            "off": {"mean": float, "n": int},
            "delta": float | None  # mean_on - mean_off, or None if either arm empty
        }
    """
    log_path = _ab_log_path(Path(project_root))

    on_values: list[int] = []
    off_values: list[int] = []

    if log_path.exists():
        for line in log_path.read_text().strip().split("\n"):
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            arm = entry.get("arm")
            tokens_before = entry.get("tokens_before", 0)
            if arm == "on":
                on_values.append(tokens_before)
            elif arm == "off":
                off_values.append(tokens_before)

    on_mean = sum(on_values) / len(on_values) if on_values else 0.0
    off_mean = sum(off_values) / len(off_values) if off_values else 0.0

    # delta is None if either arm is empty
    delta: float | None = None
    if on_values and off_values:
        delta = on_mean - off_mean

    return {
        "on": {"mean": on_mean, "n": len(on_values)},
        "off": {"mean": off_mean, "n": len(off_values)},
        "delta": delta,
    }
