"""Tests for current_round.json cleanup after merge (T-269)."""
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from agentflow.tools.cleanup_tasks import cleanup


def test_cleanup_deletes_current_round_after_merge(tmp_path):
    """After cleanup processes all round tasks merged, current_round.json is deleted."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    (tmp_path / "tasks.json").write_text(json.dumps({
        "tasks": [{"task_id": "T-001", "title": "Test task", "status": "pending"}]
    }))
    (agentflow_dir / "task_prs.json").write_text(json.dumps(
        {"T-001": "https://github.com/example/repo/pull/1"}
    ))
    (agentflow_dir / "tasks_in_flight.json").write_text(json.dumps(["T-001"]))

    # Create current_round.json with T-001
    current_round_path = agentflow_dir / "current_round.json"
    current_round_path.write_text(json.dumps({"round_id": "R-001", "task_ids": ["T-001"]}))

    mock_result = Mock()
    mock_result.stdout = "MERGED\n"
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result):
        cleanup(tmp_path)

    # Verify current_round.json was deleted when all round tasks merged
    assert not current_round_path.exists(), "current_round.json should be deleted when all round tasks complete"


def test_cleanup_idempotent_when_current_round_absent(tmp_path):
    """cleanup is idempotent: no error when current_round.json is absent."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    (tmp_path / "tasks.json").write_text(json.dumps({
        "tasks": [{"task_id": "T-001", "title": "Test task", "status": "pending"}]
    }))
    (agentflow_dir / "task_prs.json").write_text(json.dumps(
        {"T-001": "https://github.com/example/repo/pull/1"}
    ))
    (agentflow_dir / "tasks_in_flight.json").write_text(json.dumps(["T-001"]))

    # Do NOT create current_round.json

    mock_result = Mock()
    mock_result.stdout = "MERGED\n"
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result):
        cleanup(tmp_path)

    # Should complete without error
    assert not (agentflow_dir / "current_round.json").exists()


def test_cleanup_preserves_current_round_when_not_all_tasks_merged(tmp_path):
    """current_round.json is NOT deleted if only some round tasks have merged."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    (tmp_path / "tasks.json").write_text(json.dumps({
        "tasks": [
            {"task_id": "T-001", "title": "Task 1", "status": "pending"},
            {"task_id": "T-002", "title": "Task 2", "status": "pending"}
        ]
    }))
    (agentflow_dir / "task_prs.json").write_text(json.dumps({
        "T-001": "https://github.com/example/repo/pull/1",
        "T-002": "https://github.com/example/repo/pull/2"
    }))
    (agentflow_dir / "tasks_in_flight.json").write_text(json.dumps(["T-001", "T-002"]))

    # Create current_round.json with both tasks
    current_round_path = agentflow_dir / "current_round.json"
    current_round_path.write_text(json.dumps({"round_id": "R-001", "task_ids": ["T-001", "T-002"]}))

    # Mock returns MERGED for T-001 but NOT_FOUND/OPEN for T-002 (simulate only T-001 merged)
    def mock_run(cmd, *args, **kwargs):
        result = Mock()
        if "pull/1" in str(cmd):
            result.stdout = "MERGED\n"
            result.returncode = 0
        else:  # pull/2
            result.stdout = "OPEN\n"
            result.returncode = 0
        return result

    with patch("subprocess.run", side_effect=mock_run):
        cleanup(tmp_path)

    # current_round.json should still exist because T-002 is not merged
    assert current_round_path.exists(), "current_round.json should NOT be deleted when only 1 of 2 tasks merged"
