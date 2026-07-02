import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from agentflow.reporting.steady_state import (
    compute_steady_state_pct_saved,
    load_steady_state_pct_saved,
    render_replacements,
    _parse_ts,
    WINDOW_START,
)

WS = "2026-07-02T21:24:05Z"


def _session(end_time, shadow_input, shadow_output, input_tokens, output_tokens, status="closed"):
    return {
        "end_time": end_time,
        "status": status,
        "shadow_event": {"shadow_input": shadow_input, "shadow_output": shadow_output},
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def test_parse_ts_normalizes_and_rejects_bad_input():
    z = _parse_ts("2026-07-02T21:24:05Z")
    offset = _parse_ts("2026-07-02T21:24:05+00:00")
    assert z == offset
    assert _parse_ts("") is None
    assert _parse_ts("not-a-timestamp") is None


def test_compute_steady_state_pct_saved_mixed_pre_post_window():
    sessions = [
        # Pre-window: excluded, even though it has a huge saved ratio.
        _session("2026-06-25T00:00:00Z", 100_000, 10_000, 1_000, 100),
        # Post-window: included.
        _session("2026-07-03T00:00:00Z", 10_000, 1_000, 5_000, 500),
        _session("2026-07-04T00:00:00Z", 20_000, 2_000, 15_000, 1_500),
    ]
    pct = compute_steady_state_pct_saved(sessions, WS)
    # shadow_total = (10000+1000)+(20000+2000) = 33000
    # real_total   = (5000+500)+(15000+1500)   = 22000
    # saved        = 11000 -> pct = 11000/33000*100
    assert pct == (11000 / 33000) * 100


def test_compute_steady_state_pct_saved_zero_sessions_in_window():
    sessions = [
        _session("2026-06-25T00:00:00Z", 100_000, 10_000, 1_000, 100),
        _session("2026-07-01T00:00:00Z", 5_000, 500, 1_000, 100),
    ]
    assert compute_steady_state_pct_saved(sessions, WS) is None


def test_compute_steady_state_pct_saved_empty_sessions_list():
    assert compute_steady_state_pct_saved([], WS) is None


def test_compute_steady_state_pct_saved_exact_boundary_timestamp_included():
    # Session end_time == window_start exactly -- "at or after" must include it.
    sessions = [_session(WS, 10_000, 1_000, 6_000, 600)]
    pct = compute_steady_state_pct_saved(sessions, WS)
    assert pct == (11000 - 6600) / 11000 * 100


def test_compute_steady_state_pct_saved_skips_sessions_missing_shadow_data():
    sessions = [
        _session("2026-07-03T00:00:00Z", 0, 0, 5_000, 500),  # no shadow baseline -> skipped
        _session("2026-07-03T00:00:00Z", 10_000, 1_000, 5_000, 500),
    ]
    pct = compute_steady_state_pct_saved(sessions, WS)
    assert pct == ((11000 - 5500) / 11000) * 100


def test_load_steady_state_pct_saved_no_ledger_file(tmp_path):
    result = load_steady_state_pct_saved(tmp_path, WS)
    assert result["pct_saved"] is None
    assert result["n_sessions"] == 0
    assert "measured" in result["methodology"]
    assert WS in result["methodology"]


def test_load_steady_state_pct_saved_excludes_open_sessions(tmp_path):
    sessions = [
        _session("2026-07-03T00:00:00Z", 10_000, 1_000, 5_000, 500, status="open"),
        _session("2026-07-03T00:00:00Z", 10_000, 1_000, 5_000, 500, status="closed"),
    ]
    (tmp_path / "agentflow_ledger.json").write_text(json.dumps({"sessions": sessions}))
    result = load_steady_state_pct_saved(tmp_path, WS)
    assert result["n_sessions"] == 1
    assert result["pct_saved"] is not None


def test_load_steady_state_pct_saved_handles_corrupt_json(tmp_path):
    (tmp_path / "agentflow_ledger.json").write_text("{not valid json")
    result = load_steady_state_pct_saved(tmp_path, WS)
    assert result["pct_saved"] is None
    assert result["n_sessions"] == 0


def test_render_replacements_insufficient_data(tmp_path):
    replacements = render_replacements(tmp_path, WS)
    assert replacements["{steady_state_pct_str}"] == "insufficient data yet"
    assert "measured" in replacements["{steady_state_methodology_str}"]


def test_render_replacements_formats_percentage(tmp_path):
    sessions = [_session("2026-07-03T00:00:00Z", 10_000, 1_000, 5_000, 500)]
    (tmp_path / "agentflow_ledger.json").write_text(json.dumps({"sessions": sessions}))
    replacements = render_replacements(tmp_path, WS)
    assert replacements["{steady_state_pct_str}"].endswith("%")
    assert replacements["{steady_state_pct_str}"] != "insufficient data yet"


def test_window_start_constant_matches_t086_merge_time():
    assert WINDOW_START == "2026-07-02T21:24:05Z"
