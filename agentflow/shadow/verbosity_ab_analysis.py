"""A/B analysis and comparison functions for verbosity hook testing.

This module contains the analysis pipeline for computing per-arm statistics
and persisting baseline artifacts used by report_builder.py.
"""

from __future__ import annotations

import json
import math
import statistics
from datetime import datetime
from pathlib import Path

from agentflow.shadow.verbosity_ab import (
    ARMS,
    FALLBACK_BASELINE_TOKENS,
    _ab_log_path,
    _baseline_path,
    _unmeasured_baseline,
)

_UNMEASURED_ARM_STATS = {"n": 0, "mean": 0.0, "p90": 0.0, "ci95_low": None, "ci95_high": None}


def load_arm_entries(project_root: Path, arm: str) -> list[dict]:
    """Filter A/B log entries by arm."""
    from agentflow.shadow.verbosity_ab import _load_ab_entries
    return [e for e in _load_ab_entries(project_root) if e.get("arm") == arm]


def compute_arm_stats(output_tokens: list[int]) -> dict:
    """Mean / p90 / sample size / 95% CI for one arm's output_tokens."""
    n = len(output_tokens)
    if n == 0:
        return dict(_UNMEASURED_ARM_STATS)

    mean = statistics.fmean(output_tokens)
    sorted_tokens = sorted(output_tokens)
    p90 = sorted_tokens[min(int(n * 0.9), n - 1)]

    if n >= 2:
        stdev = statistics.stdev(output_tokens)
        margin = 1.96 * stdev / math.sqrt(n)
        ci_low, ci_high = mean - margin, mean + margin
    else:
        ci_low, ci_high = None, None

    return {"n": n, "mean": mean, "p90": p90, "ci95_low": ci_low, "ci95_high": ci_high}


def run_ab_comparison(project_root: Path, session_type: str | None = None) -> dict:
    """Compute per-arm stats and persist the measured hook-off baseline to
    `.agentflow/verbosity_baseline.json` for report_builder.py to consume.

    If session_type is given, only entries matching that session_type are used."""
    from agentflow.shadow.verbosity_ab import _load_ab_entries
    all_entries = _load_ab_entries(project_root)
    if session_type is not None:
        all_entries = [e for e in all_entries if e.get("session_type") == session_type]

    arm_stats = {
        arm: compute_arm_stats(
            [e.get("output_tokens", 0) for e in all_entries if e.get("arm") == arm]
        )
        for arm in ARMS
    }

    n_on = arm_stats["on"]["n"]
    n_off = arm_stats["off"]["n"]
    hook_off = arm_stats["off"]
    measured = n_off > 0
    ci_low = hook_off["ci95_low"]
    ci_high = hook_off["ci95_high"]
    ci_width = (ci_high - ci_low) if (ci_low is not None and ci_high is not None) else None

    stopping_met = (
        n_on >= 20
        and n_off >= 20
        and ci_width is not None
        and ci_width < 100
    )

    if stopping_met:
        stopping_status = f"VERBOSITY A/B COMPLETE — sufficient data (n_on={n_on}, n_off={n_off}, CI=[{round(ci_low)}, {round(ci_high)}])"
    else:
        stopping_status = f"STILL COLLECTING — n_on={n_on} / 20, n_off={n_off} / 20"

    result = {
        "computed_at": datetime.now().isoformat(),
        "baseline_tokens": round(hook_off["mean"]) if measured else FALLBACK_BASELINE_TOKENS,
        "sample_size": hook_off["n"],
        "ci95_low": hook_off["ci95_low"],
        "ci95_high": hook_off["ci95_high"],
        "measured": measured,
        "arms": arm_stats,
        "stopping_met": stopping_met,
        "stopping_status": stopping_status,
    }

    baseline_path = _baseline_path(project_root)
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def load_baseline(project_root: Path) -> dict:
    """Load the persisted baseline artifact, or an unmeasured fallback if
    run_ab_comparison()/run_verbosity_ab() has not been run yet."""
    baseline_path = _baseline_path(project_root)
    if not baseline_path.exists():
        return _unmeasured_baseline()
    try:
        return json.loads(baseline_path.read_text())
    except Exception:
        return _unmeasured_baseline()


def run_verbosity_ab(project_root: Path | None = None, session_type: str | None = None) -> dict:
    """Entry point: compare the two arms against whatever data has been
    collected so far, persist the baseline artifact, and print a short
    summary. Returns the result dict (see run_ab_comparison).

    If session_type is given, only entries matching that session_type are used."""
    root = project_root if project_root is not None else Path.cwd()
    result = run_ab_comparison(root, session_type=session_type)
    hook_on = result["arms"]["on"]
    hook_off = result["arms"]["off"]

    print("\n=== Verbosity Hook A/B Comparison ===")
    print(f"  hook_off (baseline): n={hook_off['n']:<4} mean={hook_off['mean']:.1f}  p90={hook_off['p90']:.1f}")
    print(f"  hook_on:              n={hook_on['n']:<4} mean={hook_on['mean']:.1f}  p90={hook_on['p90']:.1f}")
    if result["measured"]:
        ci = ""
        if result["ci95_low"] is not None:
            ci = f", 95% CI [{result['ci95_low']:.0f}, {result['ci95_high']:.0f}]"
        print(f"  Baseline: {result['baseline_tokens']} tokens (measured, n={result['sample_size']}{ci})")
    else:
        print(f"  Baseline: {result['baseline_tokens']} tokens (UNMEASURED fallback — collect both arms first)")
    print(f"  Stopping Criterion: {result['stopping_status']}")
    return result


if __name__ == "__main__":
    run_verbosity_ab()
