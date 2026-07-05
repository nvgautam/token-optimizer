import sys
import json
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

from agentflow.shadow.capacity_calibrator import calibrate_capacity

@pytest.fixture
def mock_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path

def test_calibrate_capacity_basic_ewma(tmp_path, mock_home):
    # Setup agentflow_ledger.json
    ledger = {
        "sessions": [
            {
                "session_id": "s1",
                "agent": "claude",
                "status": "closed",
                "start_pct_5hr": 10.0,
                "end_pct_5hr": 30.0,
                "task_ids": "T1"
            },
            {
                "session_id": "s2",
                "agent": "claude",
                "status": "closed",
                "start_pct_5hr": 80.0,
                "end_pct_5hr": 10.0,
                "task_ids": "T2, T3"
            }
        ]
    }
    
    ledger_path = tmp_path / "agentflow_ledger.json"
    ledger_path.write_text(json.dumps(ledger))
    
    # Run calibrator with current_start_pct = 40.0
    # Formula trace:
    # Default initial EWMA = 10.0, alpha = 0.3
    # Session 1: pct_consumed = 20.0, num_tasks = 1 -> pct_per_task = 20.0
    #   ewma = 0.3 * 20.0 + 0.7 * 10.0 = 13.0
    # Session 2: pct_consumed = 30.0 (reset), num_tasks = 2 -> pct_per_task = 15.0
    #   ewma = 0.3 * 15.0 + 0.7 * 13.0 = 13.6
    # current_pct_remaining = 100.0 - 40.0 = 60.0
    # tasks_remaining = floor(60.0 / 13.6) = 4
    result = calibrate_capacity(tmp_path, current_start_pct=40.0, agent="claude")
    
    assert abs(result["ewma_pct_per_task"] - 13.6) < 1e-5
    assert result["tasks_remaining"] == 4
    
    # Verify the calibration file was written
    cal_file = tmp_path / ".agentflow" / "rate_calibration_claude.json"
    assert cal_file.exists()
    cal_data = json.loads(cal_file.read_text())
    assert abs(cal_data["ewma_pct_per_task"] - 13.6) < 1e-5
    assert cal_data["tasks_remaining"] == 4

def test_calibrate_capacity_with_prior_calibration(tmp_path, mock_home):
    # Setup pre-existing calibration file
    cal_dir = tmp_path / ".agentflow"
    cal_dir.mkdir(parents=True, exist_ok=True)
    cal_file = cal_dir / "rate_calibration_gemini.json"
    cal_file.write_text(json.dumps({
        "ewma_pct_per_task": 5.0,
        "ewma_alpha": 0.5
    }))
    
    # Setup agentflow_ledger.json
    ledger = {
        "sessions": [
            {
                "session_id": "s1",
                "agent": "gemini",
                "status": "closed",
                "start_pct": 10.0,
                "end_pct": 20.0,
                "task_ids": ""
            }
        ]
    }
    
    ledger_path = tmp_path / "agentflow_ledger.json"
    ledger_path.write_text(json.dumps(ledger))
    
    # Run calibrator
    # Formula trace:
    # Prior EWMA = 5.0, alpha = 0.5
    # Session 1: pct_consumed = 10.0, num_tasks = 1 -> pct_per_task = 10.0
    #   ewma = 0.5 * 10.0 + 0.5 * 5.0 = 7.5
    # current_pct_remaining = 100.0 - 20.0 = 80.0
    # tasks_remaining = floor(80.0 / 7.5) = 10
    result = calibrate_capacity(tmp_path, current_start_pct=20.0, agent="gemini")
    
    assert abs(result["ewma_pct_per_task"] - 7.5) < 1e-5
    assert result["tasks_remaining"] == 10

def test_calibrate_capacity_graceful_fallbacks(tmp_path, mock_home):
    # 1. Missing ledger, missing calibration file
    # Default EWMA = 10.0
    # remaining = 100.0 - 50.0 = 50.0 -> tasks_remaining = 5
    result = calibrate_capacity(tmp_path, current_start_pct=50.0, agent="claude")
    assert result["ewma_pct_per_task"] == 10.0
    assert result["tasks_remaining"] == 5
    
    # 2. Corrupt ledger
    ledger_path = tmp_path / "agentflow_ledger.json"
    ledger_path.write_text("invalid json string")
    result = calibrate_capacity(tmp_path, current_start_pct=50.0, agent="claude")
    assert result["ewma_pct_per_task"] == 10.0
    assert result["tasks_remaining"] == 5
    
    # 3. Corrupt calibration file
    cal_file = tmp_path / ".agentflow" / "rate_calibration_claude.json"
    cal_file.write_text("invalid json")
    
    # Should fall back to default (10.0) or handle gracefully
    result = calibrate_capacity(tmp_path, current_start_pct=50.0, agent="claude")
    assert result["ewma_pct_per_task"] == 10.0
    assert result["tasks_remaining"] == 5


def test_capacity_calibration_report_rendering(tmp_path, mock_home):
    # Pre-create the directory structure
    cal_dir = tmp_path / ".agentflow"
    cal_dir.mkdir(parents=True, exist_ok=True)
    
    # Write rate_calibration_claude.json
    cal_file = cal_dir / "rate_calibration_claude.json"
    cal_file.write_text(json.dumps({
        "ewma_pct_per_task": 12.34,
        "tasks_remaining": 7
    }))
    
    from unittest.mock import patch
    from agentflow.reporting.report_builder import build_report
    
    out_html = tmp_path / "combined_report.html"
    
    with patch("agentflow.reporting.report_builder.get_bucketed_stats", return_value={"targeted-reads": 0, "no-reread": 0, "indexing-gap": 0, "state-docs": 0}),          patch("agentflow.reporting.report_builder.growth_tracker.compute_file_read_stats", return_value={"idx_savings": 0, "offset_savings": 0, "file_reads_real": 0, "file_reads_baseline": 0}),          patch("agentflow.reporting.report_builder._handoff_component", return_value=(0, 0, 0)),          patch("agentflow.reporting.report_builder._compression_delta_from_history", return_value=0),          patch("agentflow.reporting.report_builder.code_size_savings.load_file_families", return_value=[]):
        
        build_report(project_root=tmp_path, mode="aggregate", output_path=out_html, store_url="sqlite:///dummy.db")
        
    html = out_html.read_text()
    assert "Capacity Calibration (Claude)" in html
    assert "7 tasks remaining" in html
    assert "EWMA per task: 12.34%" in html
