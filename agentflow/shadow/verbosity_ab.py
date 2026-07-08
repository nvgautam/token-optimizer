"""A/B harness for the verbosity_reminder.py hook (T-081).

architecture.md#output-verbosity-control models the hook as saving ~350
tokens/turn (600 -> 250) but that 600-token "no hook" baseline was never
measured — it's a design-time estimate. This module builds a controlled
comparison so report_builder.py can use a measured baseline instead.

session_manager.py (agentflow/shell/session_manager.py — not owned by this
module) writes untagged per-turn entries to `.agentflow/verbosity_log.jsonl`
via `_handle_output`, in the shape {ts, session_type, turn, output_tokens}.
To compare arms without touching session_manager.py:

  1. An operator runs N sessions with AGENTFLOW_VERBOSITY_HOOK_DISABLED=1
     set (hook off) using the normal PTY shell, then imports that run's
     verbosity_log.jsonl entries into the dedicated A/B log with
     `import_from_verbosity_log(root, arm="off")`.
  2. Runs N sessions with the hook enabled (env var unset) and imports with
     `arm="on"`.
  3. Calls `run_verbosity_ab()` (or `run_ab_comparison()` directly) to
     compute per-arm mean/p90/n/95% CI and persist the measured hook-off
     baseline to `.agentflow/verbosity_baseline.json` for
     report_builder.py to read instead of the hardcoded 600.

`record_turn()` is also usable directly (e.g. from tests or a future
integration point) to append a tagged entry without going through the
import step.
"""

from __future__ import annotations

import json
import math
import statistics
import warnings
from datetime import datetime
from pathlib import Path

AB_LOG_FILENAME = "verbosity_ab_log.jsonl"
BASELINE_FILENAME = "verbosity_baseline.json"
ARMS = ("on", "off")

# Fallback used only when no A/B data has been collected yet — the original,
# never-measured design-time estimate from
# architecture.md#output-verbosity-control. Always reported alongside
# sample_size=0 / measured=False so callers can tell it apart from real data.
FALLBACK_BASELINE_TOKENS = 600

_UNMEASURED_ARM_STATS = {"n": 0, "mean": 0.0, "p90": 0.0, "ci95_low": None, "ci95_high": None}


def _ab_log_path(project_root: Path) -> Path:
    return project_root / ".agentflow" / AB_LOG_FILENAME


def _baseline_path(project_root: Path) -> Path:
    return project_root / ".agentflow" / BASELINE_FILENAME


def _unmeasured_baseline() -> dict:
    return {
        "computed_at": None,
        "baseline_tokens": FALLBACK_BASELINE_TOKENS,
        "sample_size": 0,
        "ci95_low": None,
        "ci95_high": None,
        "measured": False,
        "arms": {},
        "stopping_met": False,
        "stopping_status": "STILL COLLECTING — n_on=0 / 20, n_off=0 / 20",
    }


def record_turn(
    project_root: Path, session_type: str, turn: int, output_tokens: int, arm: str, ts: str | None = None
) -> None:
    """Append one A/B-tagged turn entry — same shape as session_manager.py's
    verbosity_log.jsonl entries, plus an `arm` field — to the dedicated
    A/B log. `ts` defaults to now(); import_from_verbosity_log passes the
    source entry's original ts through so imported entries stay identifiable
    for dedup rather than being relabeled to import time."""
    if arm not in ARMS:
        raise ValueError(f"arm must be one of {ARMS}, got {arm!r}")
    log_path = _ab_log_path(project_root)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": ts if ts is not None else datetime.now().isoformat(),
        "session_type": session_type,
        "turn": turn,
        "output_tokens": output_tokens,
        "arm": arm,
    }
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


_SENTINEL = object()


_MAX_TURNS_PER_MINUTE = 30  # sessions above this rate are bug/loop noise


def _load_ab_entries(project_root: Path) -> list[dict]:
    """Load all A/B log entries from the dedicated log file."""
    log_path = _ab_log_path(project_root)
    if not log_path.exists():
        return []
    entries = []
    for line in log_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return entries


def _anomalous_sessions(entries: list[dict]) -> set[str]:
    """Return session_ids whose turn rate exceeds _MAX_TURNS_PER_MINUTE.

    Used to exclude infinite-handoff-loop artifacts (e.g. 3,586 turns in 33
    minutes from a single session) from A/B data."""
    from collections import defaultdict
    from datetime import datetime, timezone

    by_sid: dict[str, list[str]] = defaultdict(list)
    for e in entries:
        sid = e.get("session_id")
        if sid and e.get("ts"):
            by_sid[sid].append(e["ts"])

    bad: set[str] = set()
    for sid, timestamps in by_sid.items():
        if len(timestamps) < 2:
            continue
        try:
            ts_sorted = sorted(timestamps)
            t0 = datetime.fromisoformat(ts_sorted[0]).replace(tzinfo=timezone.utc)
            t1 = datetime.fromisoformat(ts_sorted[-1]).replace(tzinfo=timezone.utc)
            minutes = max((t1 - t0).total_seconds() / 60, 1.0)
            if len(timestamps) / minutes > _MAX_TURNS_PER_MINUTE:
                bad.add(sid)
        except Exception:
            continue
    return bad


def import_from_verbosity_log(
    project_root: Path, arm: str | None = _SENTINEL, since_ts: str | None = None
) -> int:
    """Re-tag entries from the live verbosity_log.jsonl (written by
    session_manager.py during a real session) into the dedicated A/B log.
    Returns the number of entries imported.

    Sessions whose turn rate exceeds _MAX_TURNS_PER_MINUTE are excluded as
    bug/loop noise (e.g. infinite handoff loop artifacts).

    Idempotent regardless of since_ts: entries already present in the
    destination log (matched by ts+turn+session_type) are skipped,
    so re-running with no arguments never double-imports."""
    if arm is not _SENTINEL:
        warnings.warn(
            "The 'arm' parameter is deprecated and will be ignored. Arm membership is now derived from the log entries.",
            category=DeprecationWarning,
            stacklevel=2,
        )
    src_path = project_root / ".agentflow" / "verbosity_log.jsonl"
    if not src_path.exists():
        return 0

    raw: list[dict] = []
    for line in src_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            raw.append(json.loads(line))
        except Exception:
            continue

    bad_sessions = _anomalous_sessions(raw)

    already_imported = {
        (e.get("ts"), e.get("turn"), e.get("session_type"))
        for e in _load_ab_entries(project_root)
    }

    count = 0
    for entry in raw:
        if entry.get("session_id") in bad_sessions:
            continue
        if entry.get("session_type") is None:
            continue
        if "output_tokens" not in entry:
            continue
        entry_arm = entry.get("arm")
        if entry_arm not in ARMS:
            continue
        if since_ts is not None and entry.get("ts", "") <= since_ts:
            continue
        key = (entry.get("ts"), entry.get("turn", 0), entry.get("session_type", "unknown"))
        if key in already_imported:
            continue
        record_turn(
            project_root,
            session_type=entry.get("session_type", "unknown"),
            turn=entry.get("turn", 0),
            output_tokens=entry.get("output_tokens", 0),
            arm=entry_arm,
            ts=entry.get("ts"),
        )
        already_imported.add(key)
        count += 1
    return count


def __getattr__(name: str):
    """Lazy import of analysis functions to avoid circular imports."""
    if name in ("load_arm_entries", "compute_arm_stats", "run_ab_comparison", "load_baseline", "run_verbosity_ab"):
        from agentflow.shadow import verbosity_ab_analysis
        return getattr(verbosity_ab_analysis, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
