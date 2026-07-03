import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

import pytest

from agentflow.reporting.handoff_savings import (
    compute_handoff_savings,
    _percentile,
    _parse_ts,
    _session_tok_per_turn,
    _bucket_sessions,
    _triangular_sum,
    _project_session,
    _tag_breakdown_note,
)


def _session(session_id, n_turns, initial_ctx, final_ctx, end_time, status="closed"):
    return {
        "session_id": session_id,
        "end_time": end_time,
        "token_detail": {"n_turns": n_turns, "initial_ctx": initial_ctx, "final_ctx": final_ctx},
        "n_turns": n_turns,
        "final_ctx": final_ctx,
        "status": status,
    }


def _write_ledger(tmp_path, sessions):
    (tmp_path / "agentflow_ledger.json").write_text(json.dumps({"sessions": sessions, "shadow_state": {}}))


def _write_telemetry(tmp_path, events):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(exist_ok=True)
    lines = [json.dumps({"event": "handoff", "timestamp": ts, "session_type": stype}) for ts, stype in events]
    (agentflow_dir / "telemetry.jsonl").write_text("\n".join(lines) + "\n")


def test_percentile_basic():
    assert _percentile([], 25) == 0.0
    assert _percentile([5], 25) == 5
    assert _percentile([1, 2, 3, 4, 5, 6, 7, 8], 25) == pytest.approx(2.75)


def test_parse_ts_normalizes_mixed_formats():
    z = _parse_ts("2026-07-02T16:55:00Z")
    offset = _parse_ts("2026-07-02T16:55:00+00:00")
    assert z == offset
    naive = _parse_ts("2026-07-02T16:55:00")
    assert naive is not None
    assert naive.tzinfo is not None
    assert _parse_ts("") is None
    assert _parse_ts("not-a-timestamp") is None


def test_session_tok_per_turn_guards_zero_and_missing():
    assert _session_tok_per_turn(_session("a", 0, 100, 200, "t")) is None
    assert _session_tok_per_turn({"session_id": "b", "token_detail": {"n_turns": 5}}) is None
    assert _session_tok_per_turn(_session("c", 10, 1000, 6000, "t")) == 500.0


def test_triangular_sum():
    assert _triangular_sum(500, 60) == 500 * 60 * 61 / 2


def test_project_session_zero_inputs():
    result = _project_session(0, 60)
    assert result["tokens_saved"] == 0
    result = _project_session(500, 0)
    assert result["tokens_saved"] == 0


def test_project_session_produces_reduction_for_long_session():
    result = _project_session(500, 60)
    assert result["handoff_turn"] > 0
    assert result["tokens_saved"] > 0
    assert 0 < result["pct_reduction"] < 100


def test_project_session_no_handoff_when_below_threshold():
    # n_turns short enough that context never crosses THRESHOLD_TOKENS.
    result = _project_session(10, 5)
    assert result["tokens_saved"] == 0
    assert result["pct_reduction"] == 0.0


def test_bucket_sessions_falls_back_to_unbucketed_when_join_unreliable(tmp_path):
    # Only 1 telemetry event far away in time from 4 sessions -> unreliable join.
    sessions = [
        _session("a", 40, 1000, 21000, "2026-07-01T00:00:00"),
        _session("b", 50, 1000, 26000, "2026-07-01T01:00:00"),
        _session("c", 60, 1000, 31000, "2026-07-01T02:00:00"),
        _session("d", 70, 1000, 36000, "2026-07-01T03:00:00"),
    ]
    events = [(__import__("datetime").datetime.fromisoformat("2026-01-01T00:00:00+00:00"), "oracle")]
    buckets, mode = _bucket_sessions(sessions, events)
    assert mode == "unbucketed"
    assert "unbucketed" in buckets
    assert len(buckets["unbucketed"]["rates"]) == 4


def test_bucket_sessions_uses_bucketing_when_join_reliable(tmp_path):
    from datetime import datetime, timezone
    sessions = [
        _session("a", 40, 1000, 21000, "2026-07-01T00:00:00+00:00"),
        _session("b", 50, 1000, 26000, "2026-07-01T01:00:00+00:00"),
        _session("c", 60, 1000, 31000, "2026-07-01T02:00:00+00:00"),
    ]
    events = [
        (datetime(2026, 7, 1, 0, 0, 5, tzinfo=timezone.utc), "orchestrator"),
        (datetime(2026, 7, 1, 1, 0, 5, tzinfo=timezone.utc), "orchestrator"),
        (datetime(2026, 7, 1, 2, 0, 5, tzinfo=timezone.utc), "oracle"),
    ]
    buckets, mode = _bucket_sessions(sessions, events)
    assert mode == "bucketed"
    assert set(buckets.keys()) == {"orchestrator", "oracle"}
    assert len(buckets["orchestrator"]["rates"]) == 2
    assert len(buckets["oracle"]["rates"]) == 1


def test_compute_handoff_savings_no_ledger_file(tmp_path):
    result = compute_handoff_savings(tmp_path)
    assert result["tokens_saved"] == 0
    assert result["n_sessions"] == 0
    assert "N=0" in result["methodology"]


def test_compute_handoff_savings_excludes_open_sessions(tmp_path):
    sessions = [_session("a", 40, 1000, 21000, "2026-07-01T00:00:00")]
    sessions.append({"session_id": "open1", "end_time": "", "status": "open"})
    _write_ledger(tmp_path, sessions)
    result = compute_handoff_savings(tmp_path, window_start="2020-01-01T00:00:00Z")
    assert result["n_sessions"] == 1


def test_compute_handoff_savings_end_to_end_unbucketed(tmp_path):
    sessions = [
        _session(f"s{i}", 60 + i, 1000, 1000 + (600 + i * 10) * (60 + i), f"2026-07-0{1 + i % 7}T0{i % 9}:00:00")
        for i in range(10)
    ]
    _write_ledger(tmp_path, sessions)
    # No telemetry.jsonl present at all -> zero handoff events -> unbucketed.
    result = compute_handoff_savings(tmp_path, window_start="2020-01-01T00:00:00Z")
    assert result["n_sessions"] == 10
    assert result["mode"] == "unbucketed"
    assert result["tokens_saved"] > 0
    assert "p25" in result["methodology"]
    assert "modeled from N=10" in result["methodology"]


def test_tag_breakdown_note_no_events():
    assert _tag_breakdown_note([]) == "unbucketed -- no reliable session_type join"


def test_tag_breakdown_note_reports_dominant_type():
    events = [(0, "orchestrator")] * 3 + [(0, "oracle")] + [(0, None)] * 2
    note = _tag_breakdown_note(events)
    assert note == "predominantly orchestrator sessions (3 of 4 tagged handoff events)"


def test_compute_handoff_savings_unbucketed_methodology_reports_dominant_tag(tmp_path):
    sessions = [
        _session(f"s{i}", 60 + i, 1000, 1000 + (600 + i * 10) * (60 + i), f"2026-07-0{1 + i % 7}T0{i % 9}:00:00")
        for i in range(10)
    ]
    _write_ledger(tmp_path, sessions)
    # Telemetry events exist and are dominantly "orchestrator", but far too
    # sparse relative to the 10 ledger sessions to trust a per-session join
    # (mode stays "unbucketed") -- methodology should still surface the
    # population-level tag breakdown instead of a bare "no join" note.
    _write_telemetry(tmp_path, [("2099-01-01T00:00:00", "orchestrator")])
    result = compute_handoff_savings(tmp_path, window_start="2020-01-01T00:00:00Z")
    assert result["mode"] == "unbucketed"
    assert "predominantly orchestrator sessions (1 of 1 tagged handoff events)" in result["methodology"]


def test_compute_handoff_savings_methodology_never_claims_measured(tmp_path):
    sessions = [_session("a", 60, 1000, 61000, "2026-07-01T00:00:00")]
    _write_ledger(tmp_path, sessions)
    result = compute_handoff_savings(tmp_path, window_start="2020-01-01T00:00:00Z")
    assert "measured" in result["methodology"]  # "N measured sessions" is fine
    assert "directly measured" not in result["methodology"]


# --- T-089: window reconciliation with steady_state.WINDOW_START ---

def test_compute_handoff_savings_filters_by_window_start(tmp_path):
    sessions = [
        _session("before", 40, 1000, 21000, "2026-07-01T00:00:00Z"),
        _session("after", 60, 1000, 31000, "2026-07-03T00:00:00Z"),
    ]
    _write_ledger(tmp_path, sessions)
    result = compute_handoff_savings(tmp_path, window_start="2026-07-02T00:00:00Z")
    assert result["n_sessions"] == 1


def test_compute_handoff_savings_default_window_matches_steady_state():
    import inspect
    from agentflow.reporting.steady_state import WINDOW_START
    sig = inspect.signature(compute_handoff_savings)
    assert sig.parameters["window_start"].default == WINDOW_START


def test_methodology_label_includes_window(tmp_path):
    sessions = [_session("a", 60, 1000, 61000, "2026-07-03T00:00:00Z")]
    _write_ledger(tmp_path, sessions)
    result = compute_handoff_savings(tmp_path, window_start="2026-07-02T00:00:00Z")
    assert "2026-07-02T00:00:00Z" in result["methodology"]


def test_load_ledger_sessions_handles_corrupt_json(tmp_path):
    (tmp_path / "agentflow_ledger.json").write_text("{not valid json")
    from agentflow.reporting.handoff_savings import _load_ledger_sessions
    assert _load_ledger_sessions(tmp_path) == []


def test_load_handoff_events_skips_blank_and_bad_lines_and_non_handoff(tmp_path):
    from agentflow.reporting.handoff_savings import _load_handoff_events
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    lines = [
        "",
        "{not valid json",
        json.dumps({"event": "other", "timestamp": "2026-07-01T00:00:00Z"}),
        json.dumps({"event": "handoff", "timestamp": "", "session_type": "oracle"}),
        json.dumps({"event": "handoff", "timestamp": "2026-07-01T00:00:00Z", "session_type": "oracle"}),
    ]
    (agentflow_dir / "telemetry.jsonl").write_text("\n".join(lines) + "\n")
    events = _load_handoff_events(tmp_path)
    assert len(events) == 1
    assert events[0][1] == "oracle"


def test_bucket_sessions_skips_sessions_with_no_computable_rate():
    sessions = [
        _session("a", 40, 1000, 21000, "2026-07-01T00:00:00"),
        _session("zero_turns", 0, 1000, 21000, "2026-07-01T00:00:00"),
    ]
    buckets, mode = _bucket_sessions(sessions, [])
    assert sum(len(b["rates"]) for b in buckets.values()) == 1


def test_bucket_sessions_no_events_lands_unknown_bucket():
    sessions = [_session("a", 40, 1000, 21000, "2026-07-01T00:00:00")]
    buckets, mode = _bucket_sessions(sessions, [])
    assert mode == "unbucketed"
    assert len(buckets["unbucketed"]["rates"]) == 1


def test_project_session_single_turn_never_crosses_threshold():
    result = _project_session(500, 1)
    assert result["tokens_saved"] == 0
    assert result["handoff_turn"] == 0
