"""Haiku vs Sonnet subagent A/B — output token delta from model routing."""
from __future__ import annotations

import json
import statistics
from datetime import datetime
from pathlib import Path

_HAIKU_ALIASES = {"haiku", "claude-haiku-4-5-20251001"}
_SONNET_ALIASES = {"sonnet", "claude-sonnet-4-6", "claude-sonnet-4-5-20250929"}
MODELS = ("haiku", "sonnet")
MIN_SAMPLES = 5

_BASELINE_FILE = "model_ab_baseline.json"


def _normalize_model(model: str) -> str | None:
    if model in _HAIKU_ALIASES:
        return "haiku"
    if model in _SONNET_ALIASES:
        return "sonnet"
    return None


def _load_proxy_entries(project_root: Path) -> list[dict]:
    """Load .agentflow/proxy_log.jsonl, return entries that have a model field."""
    log_file = project_root / ".agentflow" / "proxy_log.jsonl"
    if not log_file.exists():
        return []
    entries = []
    try:
        for line in log_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "model" in entry:
                entries.append(entry)
    except OSError:
        pass
    return entries


def _compute_stats(tokens: list[int]) -> dict:
    """Return {"n": int, "mean": float, "p90": float}."""
    n = len(tokens)
    if n == 0:
        return {"n": 0, "mean": 0.0, "p90": 0.0}
    mean = statistics.fmean(tokens)
    sorted_tokens = sorted(tokens)
    p90 = sorted_tokens[min(int(n * 0.9), n - 1)]
    return {"n": n, "mean": mean, "p90": float(p90)}


def _unmeasured_result() -> dict:
    return {
        "computed_at": datetime.now().isoformat(),
        "measured": False,
        "delta_pct": 0.0,
        "models": {m: {"n": 0, "mean": 0.0, "p90": 0.0} for m in MODELS},
    }


def run_model_ab(project_root: Path) -> dict:
    """Load proxy_log.jsonl entries with a model field, compute per-model output
    token stats (n, mean, p90), persist to .agentflow/model_ab_baseline.json,
    and return the result dict.

    Returns an unmeasured fallback if n < MIN_SAMPLES for either arm.
    """
    entries = _load_proxy_entries(project_root)
    buckets: dict[str, list[int]] = {m: [] for m in MODELS}
    for entry in entries:
        arm = _normalize_model(entry.get("model", ""))
        if arm is None:
            continue
        buckets[arm].append(int(entry.get("output_tokens", 0)))

    model_stats = {m: _compute_stats(buckets[m]) for m in MODELS}
    h_n = model_stats["haiku"]["n"]
    s_n = model_stats["sonnet"]["n"]
    measured = h_n >= MIN_SAMPLES and s_n >= MIN_SAMPLES

    if measured:
        h_mean = model_stats["haiku"]["mean"]
        s_mean = model_stats["sonnet"]["mean"]
        delta_pct = ((s_mean - h_mean) / h_mean * 100) if h_mean > 0 else 0.0
    else:
        delta_pct = 0.0

    result = {
        "computed_at": datetime.now().isoformat(),
        "measured": measured,
        "delta_pct": round(delta_pct, 2),
        "models": model_stats,
    }

    baseline_path = project_root / ".agentflow" / _BASELINE_FILE
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        baseline_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except OSError:
        pass

    return result


def load_model_baseline(project_root: Path) -> dict:
    """Load persisted baseline from .agentflow/model_ab_baseline.json,
    or return an unmeasured fallback if absent or unreadable."""
    baseline_path = project_root / ".agentflow" / _BASELINE_FILE
    if not baseline_path.exists():
        return _unmeasured_result()
    try:
        return json.loads(baseline_path.read_text(encoding="utf-8"))
    except Exception:
        return _unmeasured_result()
