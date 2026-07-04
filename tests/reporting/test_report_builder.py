import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

import json
import pytest
from unittest.mock import MagicMock, patch
import argparse

from agentflow.shadow.analyzer import (
    _report_targeted_reads,
    _report_indexing_gap,
    _report_lazy_decomposition,
    _report_no_reread,
    _report_state_docs,
    _report_verbosity_compliance,
    main as analyzer_main
)
from agentflow.reporting.report_builder import (
    build_report,
    _reporting_window,
    _filter_by_window,
    _format_baseline_annotation,
    _load_proxy_savings,
    _compression_delta_from_history,
    _handoff_component,
    _lifetime_recycling_callout,
)
from agentflow.shadow.verbosity_ab import record_turn, run_ab_comparison
from agentflow.cli import cmd_report

@pytest.fixture
def utc_tz(monkeypatch):
    # Pin local tz to UTC so window/history comparisons are deterministic.
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.delenv("TZ", raising=False)
    time.tzset()

def test_shadow_analyzer_bucketing(tmp_path):
    tasks_data = {"tasks": [{"task_id": "T-001", "reads": ["file_a.py", "file_b.py#anchor"]}]}
    (tmp_path / "tasks.json").write_text(json.dumps(tasks_data))

    entries = [
        {"ts": "2026-07-01T12:00:00", "rel": "file_b.py", "offset": None, "idx_exists": True, "idx_sections": 4, "file_lines": 100, "file_chars": 4000},  # double-count candidate
        {"ts": "2026-07-01T12:01:00", "rel": "file_c.py", "offset": 10, "idx_exists": True, "idx_sections": 5, "file_lines": 200, "file_chars": 8000},  # targeted hit
        {"ts": "2026-07-01T12:02:00", "rel": "file_d.py", "offset": None, "idx_exists": False, "idx_sections": 0, "file_lines": 60, "file_chars": 2000},  # gap
        {"ts": "2026-07-01T12:03:00", "rel": "architecture.md", "offset": None, "idx_exists": False, "idx_sections": 0, "file_lines": 500, "file_chars": 10000},  # state doc
    ]

    from agentflow.shadow.analyzer import get_bucketed_stats

    reads_files = {"file_a.py", "file_b.py"}

    # aggregate: file_b.py matches no-reread. Value = 4000 * 0.25 = 1000.
    stats_agg = get_bucketed_stats(tmp_path, entries, reads_files, mode="aggregate")
    assert stats_agg["no-reread"] == 1000
    assert stats_agg["targeted-reads"] == 0
    assert stats_agg["indexing-gap"] == 500
    assert stats_agg["state-docs"] == 2500

    stats_by = get_bucketed_stats(tmp_path, entries, reads_files, mode="split")
    assert stats_by["no-reread"] == 1000
    assert stats_by["targeted-reads"] == 750
    assert stats_by["indexing-gap"] == 500
    assert stats_by["state-docs"] == 2500

def test_individual_reports(tmp_path):
    entries_empty = []
    assert _report_targeted_reads(entries_empty) == 0

    entries = [{"rel": "file_b.py", "offset": None, "idx_exists": True, "idx_sections": 4, "file_lines": 100, "file_chars": 4000}]
    assert _report_targeted_reads(entries) == 750

    assert _report_indexing_gap(entries_empty) == 0
    assert _report_indexing_gap(entries) == 0  # not gap because idx_exists=True
    entries_gap = [{"rel": "file_d.py", "offset": None, "idx_exists": False, "file_lines": 60, "file_chars": 2000}]
    assert _report_indexing_gap(entries_gap) == 500

    assert _report_lazy_decomposition(tmp_path) == 0
    tasks_data = {"tasks": [{"task_id": "T-001", "status": "complete"}, {"task_id": "T-002", "status": "pending", "reads": ["foo.py"]}]}
    (tmp_path / "tasks.json").write_text(json.dumps(tasks_data))
    assert _report_lazy_decomposition(tmp_path) > 0

    assert _report_no_reread(entries_empty, tmp_path) == 0
    entries_vio = [{"rel": "foo.py", "offset": None, "file_chars": 1200}]
    assert _report_no_reread(entries_vio, tmp_path) == 300

    (tmp_path / "architecture.md").write_text("Hello architecture")
    assert _report_state_docs(tmp_path) == 4

    assert _report_verbosity_compliance(tmp_path) == 0
    verb_log = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    verb_log.parent.mkdir(parents=True, exist_ok=True)
    verb_log.write_text(json.dumps({"session_type": "oracle", "output_tokens": 100}) + "\n")
    assert _report_verbosity_compliance(tmp_path) == 500

def test_analyzer_main(tmp_path):
    log_path = tmp_path / ".agentflow" / "shadow_reads.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps({"rel": "foo.py", "offset": None, "idx_exists": False, "file_lines": 60, "file_chars": 2000}) + "\n")
    (tmp_path / "tasks.json").write_text(json.dumps({"tasks": []}))
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        analyzer_main()

def test_report_builder_integration(tmp_path):
    verb_log = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    verb_log.parent.mkdir(parents=True, exist_ok=True)
    verb_log.write_text(
        json.dumps({"ts": "...", "session_type": "oracle", "turn": 1, "output_tokens": 120}) + "\n" +
        json.dumps({"ts": "...", "session_type": "oracle", "turn": 2, "output_tokens": 160}) + "\n"
    )

    # T-082: no window (no shadow_reads.jsonl) -> latest cumulative value used.
    (tmp_path / ".headroom").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".headroom" / "proxy_savings.json").write_text(json.dumps({
        "history": [{"timestamp": "2026-07-01T10:00:00Z", "total_tokens_saved": 5000, "total_input_tokens": 15000}],
    }))

    # Mock headroom lib -- deep-analytics HTML export only.
    mock_headroom = MagicMock()
    mock_storage = MagicMock()
    mock_storage.get_summary_stats.return_value = {"total_tokens_saved": 0, "total_tokens_after": 0}
    mock_headroom.storage.create_storage.return_value = mock_storage

    def mock_gen(url, path):
        Path(path).write_text("Mocked Headroom Report Content")
    mock_headroom.reporting.generator.generate_report = mock_gen

    with patch.dict(sys.modules, {"headroom": mock_headroom, "headroom.storage": mock_headroom.storage, "headroom.reporting.generator": mock_headroom.reporting.generator}):
        out_html = tmp_path / "combined_report.html"
        build_report(project_root=tmp_path, mode="aggregate", output_path=out_html, store_url="sqlite:///dummy.db")

        assert out_html.exists()
        html_content = out_html.read_text()
        assert "aggregate" in html_content.lower()
        assert "5,000" in html_content
        assert "Mocked Headroom Report Content" in html_content
        assert "Real Tokens Used" in html_content
        assert "Shadow Mode Tokens" in html_content
        assert "Percentage Saved" in html_content

# --- T-083: waste (shadow, lower=better) vs real-savings-realized split ---

def test_report_builder_splits_waste_vs_real_savings_sections(tmp_path):
    out_html = tmp_path / "combined_report.html"
    build_report(project_root=tmp_path, mode="split", output_path=out_html, store_url="sqlite:///dummy.db")
    html = out_html.read_text()
    h_waste, h_real = html.index("Waste Avoided"), html.index("Real Savings Realized")
    assert h_waste < html.index("Indexing Gap Avoidance") < h_real
    assert h_real < html.index("Output Verbosity Control") and h_real < html.index("Headroom Compression")
    assert "read volume, not savings (state-docs)" in html
    assert "Total Real Savings (total_saved)" in html and html.index("Total Real Savings") > h_real

def test_reporting_window():
    assert _reporting_window([]) is None
    assert _reporting_window([{"rel": "foo.py"}]) is None
    entries = [{"ts": "2026-07-01T12:00:00"}, {"ts": "2026-07-01T09:00:00"}, {"ts": "2026-07-01T15:00:00"}]
    assert _reporting_window(entries) == ("2026-07-01T09:00:00", "2026-07-01T15:00:00")

def test_filter_by_window():
    entries = [{"ts": "2026-07-01T12:00:00", "output_tokens": 2}]
    assert _filter_by_window(entries, None) == entries
    entries_multi = [
        {"ts": "2026-07-01T08:00:00", "output_tokens": 1},
        {"ts": "2026-07-01T12:00:00", "output_tokens": 2},
        {"ts": "2026-07-01T20:00:00", "output_tokens": 3},
    ]
    assert [e["output_tokens"] for e in _filter_by_window(entries_multi, ("2026-07-01T10:00:00", "2026-07-01T15:00:00"))] == [2]

def test_format_baseline_annotation():
    assert "UNMEASURED" in _format_baseline_annotation({"measured": False, "baseline_tokens": 600})
    assert "n=10" in _format_baseline_annotation({"measured": True, "baseline_tokens": 500, "sample_size": 10, "ci95_low": 450.0, "ci95_high": 550.0})
    assert "CI unavailable" in _format_baseline_annotation({"measured": True, "baseline_tokens": 500, "sample_size": 1, "ci95_low": None, "ci95_high": None})

def test_report_builder_uses_measured_baseline_not_hardcoded_600(tmp_path):
    for tok in (400, 500, 600):
        record_turn(tmp_path, session_type="oracle", turn=1, output_tokens=tok, arm="hook_off")
    run_ab_comparison(tmp_path)

    verb_log = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    verb_log.parent.mkdir(parents=True, exist_ok=True)
    verb_log.write_text(json.dumps({"ts": "2026-07-01T12:00:00", "session_type": "oracle", "turn": 1, "output_tokens": 100}) + "\n")

    out_html = tmp_path / "combined_report.html"
    build_report(project_root=tmp_path, mode="split", output_path=out_html, store_url="sqlite:///dummy.db")

    html_content = out_html.read_text()
    assert "400" in html_content
    assert "measured baseline=500tok" in html_content
    assert "n=3" in html_content

def test_report_builder_falls_back_when_no_baseline_measured(tmp_path):
    verb_log = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    verb_log.parent.mkdir(parents=True, exist_ok=True)
    verb_log.write_text(json.dumps({"ts": "2026-07-01T12:00:00", "session_type": "oracle", "turn": 1, "output_tokens": 100}) + "\n")

    out_html = tmp_path / "combined_report.html"
    build_report(project_root=tmp_path, mode="split", output_path=out_html, store_url="sqlite:///dummy.db")

    html_content = out_html.read_text()
    assert "UNMEASURED" in html_content
    assert "500" in html_content

def test_report_builder_aligns_verbosity_window_to_shadow_reads_scope(tmp_path):
    shadow_log = tmp_path / ".agentflow" / "shadow_reads.jsonl"
    shadow_log.parent.mkdir(parents=True, exist_ok=True)
    shadow_log.write_text(json.dumps({"ts": "2026-07-03T12:00:00", "rel": "foo.py", "offset": 1, "limit": 5, "idx_exists": True, "idx_sections": 2, "file_lines": 10, "file_chars": 400}) + "\n")

    verb_log = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    verb_log.write_text(
        json.dumps({"ts": "2026-06-01T00:00:00", "session_type": "oracle", "turn": 1, "output_tokens": 0}) + "\n" +
        json.dumps({"ts": "2026-07-03T12:00:00", "session_type": "oracle", "turn": 2, "output_tokens": 100}) + "\n"
    )

    out_html = tmp_path / "combined_report.html"
    build_report(project_root=tmp_path, mode="split", output_path=out_html, store_url="sqlite:///dummy.db")
    html_content = out_html.read_text()

    assert "500" in html_content
    assert "1,100" not in html_content

def test_cli_report_cmd(tmp_path):
    args = argparse.Namespace(mode="aggregate", output=str(tmp_path / "cli_report.html"))
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        assert cmd_report(args) == 0
        assert (tmp_path / "cli_report.html").exists()

def test_load_proxy_savings(tmp_path):
    assert _load_proxy_savings(tmp_path) is None
    (tmp_path / ".headroom").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".headroom" / "proxy_savings.json").write_text(json.dumps({"history": [{"timestamp": "t"}]}))
    assert _load_proxy_savings(tmp_path) == {"history": [{"timestamp": "t"}]}

def test_compression_delta_from_history(utc_tz):
    history = [
        {"timestamp": "2026-07-01T08:00:00Z", "total_tokens_saved": 1000, "total_input_tokens": 4000},
        {"timestamp": "2026-07-01T11:00:00Z", "total_tokens_saved": 1500, "total_input_tokens": 5000},
        {"timestamp": "2026-07-01T20:00:00Z", "total_tokens_saved": 3000, "total_input_tokens": 9000},
    ]
    window = ("2026-07-01T10:00:00", "2026-07-01T15:00:00")
    assert _compression_delta_from_history(history, window, "total_tokens_saved") == 500
    assert _compression_delta_from_history(history, window, "total_input_tokens") == 1000

    history2 = [{"timestamp": "2026-07-01T12:00:00Z", "total_tokens_saved": 800}]
    assert _compression_delta_from_history(history2, window, "total_tokens_saved") == 800

    assert _compression_delta_from_history([], ("a", "b"), "total_tokens_saved") == 0
    assert _compression_delta_from_history([], None, "total_tokens_saved") == 0
    assert _compression_delta_from_history(history2, None, "total_tokens_saved") == 800

def test_compression_delta_from_history_handles_utc_vs_local_timezone(monkeypatch):
    monkeypatch.setenv("TZ", "Etc/GMT+8")
    time.tzset()
    try:
        history = [
            {"timestamp": "2026-06-30T20:00:00Z", "total_tokens_saved": 100},
            {"timestamp": "2026-07-01T02:00:00Z", "total_tokens_saved": 900},
        ]
        window = ("2026-06-30T17:00:00", "2026-06-30T20:00:00")
        assert _compression_delta_from_history(history, window, "total_tokens_saved") == 800
    finally:
        monkeypatch.delenv("TZ", raising=False)
        time.tzset()

def test_report_builder_windows_compression_to_shadow_reads_scope(utc_tz, tmp_path):
    shadow_log = tmp_path / ".agentflow" / "shadow_reads.jsonl"
    shadow_log.parent.mkdir(parents=True, exist_ok=True)
    shadow_log.write_text(json.dumps({
        "ts": "2026-07-03T12:00:00", "rel": "foo.py", "offset": 1, "limit": 5,
        "idx_exists": True, "idx_sections": 2, "file_lines": 10, "file_chars": 400,
    }) + "\n")
    (tmp_path / ".headroom").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".headroom" / "proxy_savings.json").write_text(json.dumps({
        "history": [
            {"timestamp": "2026-07-03T09:00:00Z", "total_tokens_saved": 100, "total_input_tokens": 1000},
            {"timestamp": "2026-07-03T12:00:00Z", "total_tokens_saved": 900, "total_input_tokens": 4000},
            {"timestamp": "2026-07-03T23:00:00Z", "total_tokens_saved": 9000, "total_input_tokens": 40000},
        ],
    }))

    out_html = tmp_path / "combined_report.html"
    build_report(project_root=tmp_path, mode="split", output_path=out_html, store_url="sqlite:///dummy.db")
    html_content = out_html.read_text()
    assert "800" in html_content
    assert "9,000" not in html_content

def test_report_builder_compression_zero_when_proxy_savings_absent(tmp_path):
    out_html = tmp_path / "combined_report.html"
    build_report(project_root=tmp_path, mode="split", output_path=out_html, store_url="sqlite:///dummy.db")
    html_content = out_html.read_text()
    assert "Compression Savings" in html_content

def test_report_builder_idx_savings(tmp_path):
    shadow_log = tmp_path / ".agentflow" / "shadow_reads.jsonl"
    shadow_log.parent.mkdir(parents=True, exist_ok=True)
    shadow_log.write_text(
        json.dumps({"ts": "2026-07-03T12:00:00", "rel": "a.py", "offset": 10, "limit": 10, "idx_exists": True, "idx_sections": 1, "file_lines": 100, "file_chars": 4000}) + "\n" +
        json.dumps({"ts": "2026-07-03T12:01:00", "rel": "b.py", "offset": 5, "limit": 5, "idx_exists": False, "idx_sections": 0, "file_lines": 50, "file_chars": 2000}) + "\n"
    )
    out_html = tmp_path / "combined_report.html"
    build_report(project_root=tmp_path, mode="split", output_path=out_html, store_url="sqlite:///dummy.db")
    html_content = out_html.read_text()
    assert "Targeted Reads — Savings Realized (idx)" in html_content
    assert "900" in html_content
    assert "1,350" in html_content

def _template_html():
    return (Path(__file__).parents[2] / "agentflow" / "reporting" / "dashboard_template.html").read_text()

def test_dashboard_template_no_stale_lifetime_label():
    assert "(lifetime, all sessions)" not in _template_html()

def test_dashboard_template_cards_name_their_scope():
    html = _template_html()
    assert "File-Read" in html and "Verbosity" in html and "Compression" in html
    assert "Session-Recycling" in html and "handoff" in html.lower()

def test_handoff_component_basic(tmp_path):
    ledger = {"sessions": [
        {"status": "closed", "end_time": "2026-07-03T00:00:00Z", "input_tokens": 100, "output_tokens": 50, "shadow_event": {"shadow_input": 200, "shadow_output": 100}},
        {"status": "closed", "end_time": "2026-07-03T01:00:00Z", "input_tokens": 80, "output_tokens": 40, "shadow_event": {"shadow_input": 180, "shadow_output": 90}},
    ]}
    (tmp_path / "agentflow_ledger.json").write_text(json.dumps(ledger))
    saved, real, n = _handoff_component(tmp_path)
    assert n == 2 and saved == 300 and real == 270

def test_handoff_component_excludes_pre_window_sessions(tmp_path):
    ledger = {"sessions": [
        {"status": "closed", "end_time": "2026-01-01T00:00:00Z", "input_tokens": 100, "output_tokens": 50,
         "shadow_event": {"shadow_input": 200, "shadow_output": 100}},
    ]}
    (tmp_path / "agentflow_ledger.json").write_text(json.dumps(ledger))
    saved, real, n = _handoff_component(tmp_path)
    assert (saved, real, n) == (0, 0, 0)

def test_handoff_component_empty_ledger(tmp_path):
    assert _handoff_component(tmp_path) == (0, 0, 0)

def test_build_report_pct_includes_handoff_and_compression(tmp_path):
    out_html = tmp_path / "combined_report.html"
    with patch("agentflow.reporting.report_builder._handoff_component", return_value=(1000, 5000, 3)), \
         patch("agentflow.reporting.report_builder._compression_delta_from_history", return_value=2000):
        build_report(project_root=tmp_path, mode="aggregate", output_path=out_html, store_url="sqlite:///dummy.db")
    html = out_html.read_text()
    assert "37.5%" in html
    assert "included in combined %" in html

def test_lifetime_recycling_callout_sums_all_sessions(tmp_path):
    ledger = {"sessions": [
        {"status": "closed", "end_time": "2026-01-01T00:00:00Z", "input_tokens": 100, "output_tokens": 50,
         "shadow_event": {"shadow_extra": 30}},
        {"status": "closed", "end_time": "2026-07-03T00:00:00Z", "input_tokens": 200, "output_tokens": 80,
         "shadow_event": {"shadow_extra": 50}},
    ]}
    (tmp_path / "agentflow_ledger.json").write_text(json.dumps(ledger))
    extra, real, n = _lifetime_recycling_callout(tmp_path)
    assert extra == 80 and real == 430 and n == 2

def test_lifetime_recycling_callout_empty(tmp_path):
    assert _lifetime_recycling_callout(tmp_path) == (0, 0, 0)

def test_report_builder_pct_of_total(tmp_path):
    out_html = tmp_path / "combined_report.html"
    with patch("agentflow.reporting.report_builder.get_bucketed_stats", return_value={"targeted-reads": 0, "no-reread": 0, "indexing-gap": 0, "state-docs": 0}), \
         patch("agentflow.reporting.report_builder.growth_tracker.compute_file_read_stats", return_value={"idx_savings": 1000, "offset_savings": 0, "file_reads_real": 0, "file_reads_baseline": 0}), \
         patch("agentflow.reporting.report_builder._handoff_component", return_value=(3000, 5000, 3)), \
         patch("agentflow.reporting.report_builder._compression_delta_from_history", return_value=3000), \
         patch("agentflow.reporting.report_builder.load_baseline", return_value={"baseline_tokens": 2000, "measured": True, "sample_size": 3, "ci95_low": 1800, "ci95_high": 2200}), \
         patch("agentflow.reporting.report_builder._filter_by_window", return_value=[{"output_tokens": 0}]), \
         patch("agentflow.reporting.report_builder.code_size_savings.load_file_families", return_value=[]), \
         patch("agentflow.reporting.report_builder.code_size_savings.compute_code_size_savings", return_value={"total_saved_tokens": 1000}):
        
        build_report(project_root=tmp_path, mode="aggregate", output_path=out_html, store_url="sqlite:///dummy.db")
        
    html = out_html.read_text()
    
    assert "10.0% of total" in html
    assert "20.0% of total" in html
    assert "30.0% of total" in html
    assert "30.0% of total" in html
    assert "10.0% of total" in html


def test_verbosity_ab_stopping_criterion(tmp_path):
    # Test (1): Stopping criterion is not met initially (low sample size)
    from agentflow.shadow.verbosity_ab import run_ab_comparison, import_from_verbosity_log
    
    # Pre-create the directory structure
    af_dir = tmp_path / ".agentflow"
    af_dir.mkdir(parents=True, exist_ok=True)
    
    # Create empty verbosity_log
    (af_dir / "verbosity_log.jsonl").write_text("")
    
    res = run_ab_comparison(tmp_path)
    assert res["stopping_met"] is False
    assert "STILL COLLECTING" in res["stopping_status"]
    assert "n_on=0 / 20" in res["stopping_status"]
    
    # Test (2): Add sufficient entries to meet the criterion
    # We need n_on >= 20, n_off >= 20, and CI width for hook_off < 100.
    log_content = ""
    for i in range(20):
        log_content += json.dumps({"ts": f"2026-07-04T12:00:{i:02d}", "session_type": "oracle", "turn": i + 1, "output_tokens": 100, "arm": "hook_on"}) + "\n"
        log_content += json.dumps({"ts": f"2026-07-04T12:01:{i:02d}", "session_type": "oracle", "turn": i + 1, "output_tokens": 100, "arm": "hook_off"}) + "\n"
        
    (af_dir / "verbosity_log.jsonl").write_text(log_content)
    
    import_from_verbosity_log(tmp_path)
    res = run_ab_comparison(tmp_path)
    
    assert res["stopping_met"] is True
    assert "VERBOSITY A/B COMPLETE" in res["stopping_status"]
    assert "n_on=20, n_off=20" in res["stopping_status"]
    
    # Test (3): Verify build_report output renders the banner correctly
    out_html = tmp_path / "combined_report.html"
    
    with patch("agentflow.reporting.report_builder.get_bucketed_stats", return_value={"targeted-reads": 0, "no-reread": 0, "indexing-gap": 0, "state-docs": 0}), \
         patch("agentflow.reporting.report_builder.growth_tracker.compute_file_read_stats", return_value={"idx_savings": 0, "offset_savings": 0, "file_reads_real": 0, "file_reads_baseline": 0}), \
         patch("agentflow.reporting.report_builder._handoff_component", return_value=(0, 0, 0)), \
         patch("agentflow.reporting.report_builder._compression_delta_from_history", return_value=0), \
         patch("agentflow.reporting.report_builder.code_size_savings.load_file_families", return_value=[]):
        
        build_report(project_root=tmp_path, mode="aggregate", output_path=out_html, store_url="sqlite:///dummy.db")
        
    html = out_html.read_text()
    assert "VERBOSITY A/B COMPLETE" in html
    assert "sufficient data" in html


