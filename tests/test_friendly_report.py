"""Tests for agentflow.shadow.friendly_report — aggregate savings dashboard."""
import json
import pytest
from pathlib import Path

SONNET_INPUT_RATE = 3.0 / 1_000_000
CAP = 310_230_774


def _ledger(tmp_path: Path, sessions: list) -> Path:
    p = tmp_path / "agentflow_ledger.json"
    p.write_text(json.dumps({"sessions": sessions, "usage_snapshots": []}))
    return p


def _sess(start: float, end: float, n_turns: int = 10, ctx: int = 50_000, status: str = "closed") -> dict:
    return {
        "status": status, "agent": "claude",
        "start_pct_5hr": start, "end_pct_5hr": end,
        "token_detail": {"n_turns": n_turns, "final_ctx": ctx},
        "cap_5hr": CAP,
    }


# 1. Aggregate totals match sum of per-session savings
def test_aggregate_totals_match(tmp_path):
    from agentflow.shadow.friendly_report import compute_friendly_report
    sessions = [_sess(10.0, 25.0, 15, 80_000), _sess(5.0, 30.0, 20, 100_000)]
    report = compute_friendly_report(_ledger(tmp_path, sessions))
    expected = sum(s["tokens_saved"] for s in report["sessions"])
    assert report["tokens_saved"] == expected
    assert abs(report["usd_saved"] - expected * SONNET_INPUT_RATE) < 1e-6


# 2. No strategy-level keys exposed
def test_no_strategy_keys_in_output(tmp_path):
    from agentflow.shadow.friendly_report import compute_friendly_report
    report = compute_friendly_report(_ledger(tmp_path, [_sess(10.0, 20.0)]))
    all_keys: set[str] = set(report.keys())
    for s in report.get("sessions", []):
        all_keys.update(s.keys())
    forbidden = {"targeted_reads", "verbosity", "headroom", "no_reread"}
    assert not (all_keys & forbidden), f"Strategy keys exposed: {all_keys & forbidden}"


# 3. Empty / missing ledger → zero-state, no crash
def test_empty_ledger_zero_state(tmp_path):
    from agentflow.shadow.friendly_report import compute_friendly_report
    report = compute_friendly_report(_ledger(tmp_path, []))
    assert report == {"session_count": 0, "tokens_saved": 0, "usd_saved": 0.0, "sessions": []}


def test_missing_ledger_zero_state(tmp_path):
    from agentflow.shadow.friendly_report import compute_friendly_report
    report = compute_friendly_report(tmp_path / "nonexistent.json")
    assert report["session_count"] == 0
    assert report["tokens_saved"] == 0
    assert report["usd_saved"] == 0.0


# 4. Only closed sessions are counted
def test_session_count(tmp_path):
    from agentflow.shadow.friendly_report import compute_friendly_report
    sessions = [
        _sess(0.0, 10.0, 5, 30_000),
        _sess(10.0, 20.0, 8, 40_000),
        _sess(20.0, 22.0, 2, 10_000, status="open"),
    ]
    report = compute_friendly_report(_ledger(tmp_path, sessions))
    assert report["session_count"] == 2


# 5. Sparkline has one char per session
def test_sparkline_length(tmp_path):
    from agentflow.shadow.friendly_report import compute_friendly_report, render_text_report
    sessions = [_sess(float(i), float(i + 5)) for i in range(0, 40, 5)]
    report = compute_friendly_report(_ledger(tmp_path, sessions))
    text = render_text_report(report)
    spark_chars = "▁▂▃▄▅▆▇█"
    spark_line = next((ln for ln in text.splitlines() if any(c in ln for c in spark_chars)), None)
    assert spark_line is not None, "No sparkline in output"
    spark = spark_line.strip().split()[0]
    assert len(spark) == report["session_count"]


# 6. Pct wraparound: end_pct < start_pct → (100-start)+end
def test_pct_wraparound(tmp_path):
    from agentflow.shadow.friendly_report import compute_friendly_report
    sess = _sess(90.0, 10.0, 15, 80_000)
    report = compute_friendly_report(_ledger(tmp_path, [sess]))
    delta = (100.0 - 90.0) + 10.0  # = 20
    tokens_consumed = delta / 100.0 * CAP
    waste = 15 * 80_000 / 2.0
    expected = int(max(0.0, waste - tokens_consumed))
    assert report["tokens_saved"] == pytest.approx(expected, abs=1)
