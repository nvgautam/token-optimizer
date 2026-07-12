import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

import json
import pytest
from unittest.mock import patch

from agentflow.reporting.model_routing import tokens_to_usd, model_routing_savings, PRICING
from agentflow.reporting.report_builder import build_report

# --- T-098: Model Routing Savings ---

def test_tokens_to_usd_haiku():
    td = {"uncached_input": 1_000_000, "cache_creation": 0, "cache_read": 0, "output": 0}
    cost = tokens_to_usd(td, "haiku")
    assert abs(cost - PRICING["haiku"]["uncached_input"]) < 1e-9


def test_tokens_to_usd_sonnet_output():
    td = {"uncached_input": 0, "cache_creation": 0, "cache_read": 0, "output": 1_000_000}
    cost = tokens_to_usd(td, "sonnet")
    assert abs(cost - PRICING["sonnet"]["output"]) < 1e-9


def test_tokens_to_usd_sonnet_more_expensive_than_haiku():
    td = {"uncached_input": 500_000, "cache_creation": 100_000, "cache_read": 200_000, "output": 300_000}
    assert tokens_to_usd(td, "sonnet") > tokens_to_usd(td, "haiku")


def test_model_routing_savings_empty_ledger(tmp_path):
    result = model_routing_savings(tmp_path)
    assert result == {"usd_saved": 0.0, "haiku_tasks": 0, "token_saved_equivalent": 0}


def test_model_routing_savings_no_model_field(tmp_path):
    ledger = {"sessions": [{"task_ids": "T-001", "token_detail": {"uncached_input": 100_000, "output": 50_000}}]}
    (tmp_path / "agentflow_ledger.json").write_text(json.dumps(ledger))
    (tmp_path / "tasks.json").write_text(json.dumps({"tasks": [{"task_id": "T-001", "status": "pending"}]}))
    result = model_routing_savings(tmp_path)
    assert result["usd_saved"] == 0.0 and result["haiku_tasks"] == 0


def test_model_routing_savings_haiku_task_saves_usd(tmp_path):
    td = {"uncached_input": 0, "cache_creation": 0, "cache_read": 0, "output": 1_000_000}
    ledger = {"sessions": [{"task_ids": "T-001", "token_detail": td}]}
    tasks = {"tasks": [{"task_id": "T-001", "model": "haiku", "status": "pending"}]}
    (tmp_path / "agentflow_ledger.json").write_text(json.dumps(ledger))
    (tmp_path / "tasks.json").write_text(json.dumps(tasks))
    result = model_routing_savings(tmp_path)
    expected_saving = PRICING["sonnet"]["output"] - PRICING["haiku"]["output"]
    assert abs(result["usd_saved"] - expected_saving) < 1e-6
    assert result["haiku_tasks"] == 1
    assert result["token_saved_equivalent"] > 0


def test_report_includes_model_routing_row(tmp_path):
    out_html = tmp_path / "combined_report.html"
    with patch("agentflow.reporting.report_builder.get_bucketed_stats", return_value={"targeted-reads": 0, "no-reread": 0, "indexing-gap": 0, "state-docs": 0}), \
         patch("agentflow.reporting.report_builder.growth_tracker.compute_file_read_stats", return_value={"idx_savings": 0, "offset_savings": 0, "file_reads_real": 0, "file_reads_baseline": 0}), \
         patch("agentflow.reporting.report_builder._handoff_component", return_value=(0, 0, 0)), \
         patch("agentflow.reporting.report_builder._compression_delta_from_history", return_value=0), \
         patch("agentflow.reporting.report_builder.code_size_savings.load_file_families", return_value=[]):
        build_report(project_root=tmp_path, mode="aggregate", output_path=out_html, store_url="sqlite:///dummy.db")
    html = out_html.read_text()
    assert "Model Routing" in html
    assert "model-routing" in html
