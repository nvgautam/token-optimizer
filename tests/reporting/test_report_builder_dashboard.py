import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

import json
import pytest
from unittest.mock import patch

from agentflow.reporting.report_builder import (
    build_report,
    _handoff_component,
    _lifetime_recycling_callout,
)

@pytest.fixture
def utc_tz(monkeypatch):
    # Pin local tz to UTC so window/history comparisons are deterministic.
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.delenv("TZ", raising=False)
    time.tzset()

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
