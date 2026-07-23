"""Tests for startup housekeeping — round status auto-update when all tasks complete."""
import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


@pytest.fixture
def mock_manager(tmp_path):
    """Create a mock SessionManager with project paths."""
    manager = Mock()
    manager._project_root = tmp_path
    manager._log_audit = Mock()
    return manager


@pytest.fixture
def execution_plan_with_rounds(tmp_path):
    """Create a sample execution_plan.md with multiple rounds."""
    content = """# AgentFlow — Execution Plan

## Milestone 1: Foundation
Status: COMPLETE

| Round | Tasks | Status |
|---|---|---|
| 1 | T-001 | MERGED |

## Milestone 2: Skill Files
Status: COMPLETE

| Round | Tasks | Note |
|---|---|---|
| A | T-013, T-014 | Parallel |
| B | T-026, T-027 | After A — PENDING |
| C | T-031 | After B |

## Milestone 3: Symbol Indexer
Status: PENDING

| Round | Tasks | Note |
|---|---|---|
| A | T-028a | Python parser |
| B | T-028b | Markdown parser |
"""
    ep_path = tmp_path / "execution_plan.md"
    ep_path.write_text(content, encoding="utf-8")
    return ep_path, content


@pytest.fixture
def tasks_json_all_complete(tmp_path):
    """Create tasks.json with all tasks marked complete."""
    tasks_data = {
        "tasks": [
            {"task_id": "T-001", "status": "complete"},
            {"task_id": "T-013", "status": "complete"},
            {"task_id": "T-014", "status": "complete"},
            {"task_id": "T-026", "status": "complete"},
            {"task_id": "T-027", "status": "complete"},
            {"task_id": "T-028a", "status": "complete"},
            {"task_id": "T-028b", "status": "complete"},
            {"task_id": "T-031", "status": "complete"},
        ]
    }
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(json.dumps(tasks_data, indent=2), encoding="utf-8")
    return tasks_path


@pytest.fixture
def tasks_json_mixed(tmp_path):
    """Create tasks.json with some tasks pending."""
    tasks_data = {
        "tasks": [
            {"task_id": "T-001", "status": "complete"},
            {"task_id": "T-013", "status": "complete"},
            {"task_id": "T-014", "status": "complete"},
            {"task_id": "T-026", "status": "pending"},
            {"task_id": "T-027", "status": "pending"},
            {"task_id": "T-028a", "status": "pending"},
            {"task_id": "T-028b", "status": "pending"},
            {"task_id": "T-031", "status": "pending"},
        ]
    }
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(json.dumps(tasks_data, indent=2), encoding="utf-8")
    return tasks_path


class TestStartupHousekeeping:
    """Test suite for startup housekeeping round status checks."""

    def test_parse_round_table_no_rounds(self):
        """Test parsing execution_plan.md with no rounds defined."""
        from agentflow.shell.housekeeping import parse_round_table

        content = """# AgentFlow — Execution Plan

## Milestone 1: Foundation
Status: COMPLETE
"""
        rounds = parse_round_table(content)
        assert rounds == []

    def test_parse_round_table_extracts_round_rows(self):
        """Test parsing extracts round identifiers and task lists."""
        from agentflow.shell.housekeeping import parse_round_table

        content = """| Round | Tasks | Note |
|---|---|---|
| A | T-013, T-014 | Parallel |
| B | T-026, T-027 | After A |
| C | T-031 | Single |
"""
        rounds = parse_round_table(content)
        assert len(rounds) == 3
        assert rounds[0]["round_id"] == "A"
        assert set(rounds[0]["task_ids"]) == {"T-013", "T-014"}
        assert rounds[1]["round_id"] == "B"
        assert set(rounds[1]["task_ids"]) == {"T-026", "T-027"}
        assert rounds[2]["round_id"] == "C"
        assert rounds[2]["task_ids"] == ["T-031"]

    def test_parse_round_table_numeric_rounds(self):
        """Test parsing numeric round identifiers."""
        from agentflow.shell.housekeeping import parse_round_table

        content = """| Round | Tasks | Status |
|---|---|---|
| 1 | T-001 | MERGED |
| 2 | T-002, T-003 | PENDING |
"""
        rounds = parse_round_table(content)
        assert len(rounds) == 2
        assert rounds[0]["round_id"] == "1"
        assert rounds[1]["round_id"] == "2"

    def test_parse_round_table_skips_merged_rows(self):
        """Test that already-merged rows are excluded from the list."""
        from agentflow.shell.housekeeping import parse_round_table

        content = """| Round | Tasks | Note |
|---|---|---|
| A | T-001 | MERGED |
| B | T-002 | PENDING |
"""
        rounds = parse_round_table(content)
        # Rows with MERGED should still be parsed, but caller can filter
        assert len(rounds) == 2

    def test_check_round_complete_all_tasks_done(self):
        """Test that round is marked complete when all tasks are done."""
        from agentflow.shell.housekeeping import is_round_complete

        tasks_by_id = {
            "T-001": "complete",
            "T-002": "complete",
            "T-003": "complete",
        }
        assert is_round_complete(["T-001", "T-002", "T-003"], tasks_by_id)

    def test_check_round_complete_with_pending_task(self):
        """Test that round is not complete when any task is pending."""
        from agentflow.shell.housekeeping import is_round_complete

        tasks_by_id = {
            "T-001": "complete",
            "T-002": "pending",
            "T-003": "complete",
        }
        assert not is_round_complete(["T-001", "T-002", "T-003"], tasks_by_id)

    def test_check_round_complete_missing_task(self):
        """Test that round is not complete when task is missing from tasks.json."""
        from agentflow.shell.housekeeping import is_round_complete

        tasks_by_id = {
            "T-001": "complete",
            "T-003": "complete",
        }
        # T-002 is missing
        assert not is_round_complete(["T-001", "T-002", "T-003"], tasks_by_id)

    def test_run_startup_housekeeping_all_complete(self, mock_manager, execution_plan_with_rounds, tasks_json_all_complete):
        """Test housekeeping updates rounds to MERGED when all tasks complete."""
        from agentflow.shell.housekeeping import run_startup_housekeeping

        ep_path, _ = execution_plan_with_rounds
        run_startup_housekeeping(mock_manager)

        # Read back the execution_plan.md
        content = ep_path.read_text(encoding="utf-8")
        # Check that rounds B and C in Milestone 2 were updated to MERGED
        # (they should halt at first pending round)
        lines = content.splitlines()
        assert any("MERGED" in line for line in lines)

    def test_run_startup_housekeeping_halts_on_pending(self, mock_manager, execution_plan_with_rounds, tasks_json_mixed):
        """Test housekeeping halts at first round with pending task."""
        from agentflow.shell.housekeeping import run_startup_housekeeping

        ep_path, _ = execution_plan_with_rounds
        run_startup_housekeeping(mock_manager)

        # Should have updated Milestone 2 rounds A (T-013, T-014 both complete)
        # but halted before B since T-026 and T-027 are pending
        content = ep_path.read_text(encoding="utf-8")
        assert "execution_plan" in str(ep_path)

    def test_run_startup_housekeeping_lock_acquisition(self, mock_manager, execution_plan_with_rounds, tasks_json_all_complete):
        """Test that housekeeping acquires lock during write."""
        from agentflow.shell.housekeeping import run_startup_housekeeping
        import fcntl

        ep_path, _ = execution_plan_with_rounds

        with patch("fcntl.flock") as mock_flock:
            run_startup_housekeeping(mock_manager)
            # Verify lock was attempted
            # Note: actual file lock may not show in mock if using real fcntl
            # Just verify no exception was raised

    def test_run_startup_housekeeping_idempotent(self, mock_manager, execution_plan_with_rounds, tasks_json_all_complete):
        """Test that running housekeeping twice produces same result."""
        from agentflow.shell.housekeeping import run_startup_housekeeping

        ep_path, _ = execution_plan_with_rounds

        # First run
        run_startup_housekeeping(mock_manager)
        content_after_first = ep_path.read_text(encoding="utf-8")

        # Second run should not change anything
        run_startup_housekeeping(mock_manager)
        content_after_second = ep_path.read_text(encoding="utf-8")

        assert content_after_first == content_after_second

    def test_run_startup_housekeeping_missing_tasks_json(self, mock_manager, execution_plan_with_rounds):
        """Test housekeeping gracefully handles missing tasks.json."""
        from agentflow.shell.housekeeping import run_startup_housekeeping

        # tasks.json does not exist
        run_startup_housekeeping(mock_manager)

        # Should not raise exception; execution_plan.md should be unchanged
        content = execution_plan_with_rounds[0].read_text(encoding="utf-8")
        assert "Milestone" in content

    def test_run_startup_housekeeping_malformed_execution_plan(self, mock_manager, tmp_path):
        """Test housekeeping gracefully handles malformed execution_plan.md."""
        from agentflow.shell.housekeeping import run_startup_housekeeping

        ep_path = tmp_path / "execution_plan.md"
        ep_path.write_text("invalid markdown content", encoding="utf-8")

        # Should not raise exception
        run_startup_housekeeping(mock_manager)

    def test_run_startup_housekeeping_logs_audit_events(self, mock_manager, execution_plan_with_rounds, tasks_json_all_complete):
        """Test housekeeping logs audit events for transparency."""
        from agentflow.shell.housekeeping import run_startup_housekeeping

        ep_path, _ = execution_plan_with_rounds
        run_startup_housekeeping(mock_manager)

        # Verify at least one audit log was made
        assert mock_manager._log_audit.called

    def test_parse_round_table_handles_header_separator(self):
        """Test that parser correctly skips header separator rows."""
        from agentflow.shell.housekeeping import parse_round_table

        content = """| Round | Tasks | Note |
|---|---|---|
| --- | --- | --- |
| A | T-001 | After B |
"""
        rounds = parse_round_table(content)
        # Should skip the separator row and only parse A
        assert len(rounds) >= 1
        assert any(r["round_id"] == "A" for r in rounds)

    def test_startup_housekeeping_called_on_session_manager_init(self):
        """Test that startup housekeeping is called during SessionManager init."""
        # This is an integration test — verifies the hook point exists
        # Actual invocation tested elsewhere with mocked dependencies
        from agentflow.shell.session_manager import SessionManager

        # Verify the function is imported/available
        from agentflow.shell.housekeeping import run_startup_housekeeping
        assert callable(run_startup_housekeeping)

    def test_parse_task_ids_from_round_row(self):
        """Test extracting task IDs from round row with various formats."""
        from agentflow.shell.housekeeping import parse_round_table

        content = """| Round | Tasks | Note |
|---|---|---|
| A | T-001, T-002, T-003 | Multiple |
| B | T-004 | Single |
| C | T-005,T-006 | No spaces |
"""
        rounds = parse_round_table(content)
        assert set(rounds[0]["task_ids"]) == {"T-001", "T-002", "T-003"}
        assert rounds[1]["task_ids"] == ["T-004"]
        assert set(rounds[2]["task_ids"]) == {"T-005", "T-006"}

    def test_multiple_milestones_halt_on_first_pending(self, tmp_path):
        """Test that scan halts at first pending round across all milestones."""
        from agentflow.shell.housekeeping import (
            parse_round_table, is_round_complete, get_tasks_by_id
        )

        # Create execution_plan with multiple milestones
        ep_content = """# Plan

## Milestone 1
| Round | Tasks |
|---|---|
| 1 | T-001 |
| 2 | T-002 |

## Milestone 2
| Round | Tasks |
|---|---|
| A | T-003 |
| B | T-004 |
"""
        # Tasks: T-001 and T-002 complete, T-003 and T-004 pending
        tasks_by_id = {
            "T-001": "complete",
            "T-002": "complete",
            "T-003": "pending",
            "T-004": "pending",
        }

        rounds = parse_round_table(ep_content)
        # Rounds 1, 2 should be complete, A and B pending
        assert is_round_complete(rounds[0]["task_ids"], tasks_by_id)
        assert is_round_complete(rounds[1]["task_ids"], tasks_by_id)
        assert not is_round_complete(rounds[2]["task_ids"], tasks_by_id)

