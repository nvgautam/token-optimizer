"""Tests for T-014: TokenTracker."""

import json

import pytest

from agentflow.config.schema import AgentFlowConfig, TokenBudgetConfig
from agentflow.telemetry.token_tracker import BudgetStatus, TokenTracker


def make_config(per_worker: int = 50000) -> AgentFlowConfig:
    cfg = AgentFlowConfig()
    cfg.token_budget = TokenBudgetConfig(per_worker=per_worker, reviewer=20000)
    return cfg


def make_tracker(tmp_path, per_worker: int = 50000) -> TokenTracker:
    return TokenTracker(cwd=tmp_path, config=make_config(per_worker))


def test_track_span_appends_record_to_ledger(tmp_path):
    tracker = make_tracker(tmp_path)
    tracker.track_span("T-001", "worker.api_call", 1000, 200)
    ledger = json.loads((tmp_path / ".agentflow" / "ledger.json").read_text())
    assert len(ledger) == 1
    assert ledger[0]["task_id"] == "T-001"
    assert ledger[0]["tokens_in"] == 1000
    assert ledger[0]["tokens_out"] == 200
    assert ledger[0]["record_type"] == "span"


def test_session_total_sums_tokens_for_task(tmp_path):
    tracker = make_tracker(tmp_path)
    tracker.track_span("T-001", "worker.api_call", 1000, 200)
    tracker.track_span("T-001", "worker.api_call", 500, 100)
    assert tracker.session_total("T-001") == 1800


def test_track_span_returns_ok_below_80pct(tmp_path):
    tracker = make_tracker(tmp_path, per_worker=10000)
    result = tracker.track_span("T-001", "worker.api_call", 500, 100)
    assert result.status == BudgetStatus.OK


def test_track_span_returns_warning_at_80pct(tmp_path):
    tracker = make_tracker(tmp_path, per_worker=1000)
    result = tracker.track_span("T-001", "worker.api_call", 720, 80)
    assert result.status == BudgetStatus.WARNING


def test_track_span_returns_exceeded_at_100pct(tmp_path):
    tracker = make_tracker(tmp_path, per_worker=1000)
    result = tracker.track_span("T-001", "worker.api_call", 900, 100)
    assert result.status == BudgetStatus.EXCEEDED


def test_budget_exceeded_is_returned_not_raised(tmp_path):
    tracker = make_tracker(tmp_path, per_worker=100)
    result = tracker.track_span("T-001", "worker.api_call", 5000, 1000)
    assert result.status == BudgetStatus.EXCEEDED


def test_shadow_total_gte_project_total_for_multiple_tasks(tmp_path):
    tracker = make_tracker(tmp_path)
    tracker.track_span("T-001", "worker.api_call", 1000, 500)
    tracker.track_span("T-002", "worker.api_call", 1000, 500)
    assert tracker.shadow_total() >= tracker.project_total()


def test_shadow_total_equals_project_total_for_single_task(tmp_path):
    tracker = make_tracker(tmp_path)
    tracker.track_span("T-001", "worker.api_call", 1000, 500)
    assert tracker.shadow_total() == tracker.project_total()


def test_project_total_aggregates_all_tasks(tmp_path):
    tracker = make_tracker(tmp_path)
    tracker.track_span("T-001", "worker.api_call", 1000, 200)
    tracker.track_span("T-002", "worker.api_call", 800, 150)
    assert tracker.project_total() == 2150


def test_close_session_writes_session_close_record(tmp_path):
    tracker = make_tracker(tmp_path)
    tracker.track_span("T-001", "worker.api_call", 500, 100)
    tracker.close_session("T-001", status="pr_opened")
    ledger = json.loads((tmp_path / ".agentflow" / "ledger.json").read_text())
    close_records = [r for r in ledger if r.get("record_type") == "session_close"]
    assert len(close_records) == 1
    assert close_records[0]["status"] == "pr_opened"
    assert close_records[0]["task_id"] == "T-001"


def test_ledger_persists_across_tracker_instances(tmp_path):
    tracker1 = make_tracker(tmp_path)
    tracker1.track_span("T-001", "worker.api_call", 1000, 200)

    tracker2 = make_tracker(tmp_path)
    assert tracker2.session_total("T-001") == 1200


def test_ledger_string_values_under_200_chars(tmp_path):
    tracker = make_tracker(tmp_path)
    tracker.track_span("T-001", "worker.api_call", 1000, 200)
    tracker.close_session("T-001")
    ledger = json.loads((tmp_path / ".agentflow" / "ledger.json").read_text())
    for record in ledger:
        for value in record.values():
            if isinstance(value, str):
                assert len(value) <= 200, f"String too long: {value[:50]}..."
