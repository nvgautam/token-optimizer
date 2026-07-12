import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

import json
import pytest
from unittest.mock import patch

from agentflow.reporting.report_builder import build_report
from agentflow.shadow.verbosity_ab import run_ab_comparison, import_from_verbosity_log

@pytest.fixture
def utc_tz(monkeypatch):
    # Pin local tz to UTC so window/history comparisons are deterministic.
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.delenv("TZ", raising=False)
    time.tzset()

def test_verbosity_ab_stopping_criterion(tmp_path):
    # Test (1): Stopping criterion is not met initially (low sample size)

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
        log_content += json.dumps({"ts": f"2026-07-04T12:00:{i:02d}", "session_type": "oracle", "turn": i + 1, "output_tokens": 100, "arm": "on"}) + "\n"
        log_content += json.dumps({"ts": f"2026-07-04T12:01:{i:02d}", "session_type": "oracle", "turn": i + 1, "output_tokens": 100, "arm": "off"}) + "\n"

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
