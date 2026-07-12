import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

import json
import pytest
from unittest.mock import MagicMock, patch
import argparse

from agentflow.reporting.report_builder import (
    build_report,
    _reporting_window,
    _filter_by_window,
    _format_baseline_annotation,
    _load_proxy_savings,
    _compression_delta_from_history,
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
        record_turn(tmp_path, session_type="oracle", turn=1, output_tokens=tok, arm="off")
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
