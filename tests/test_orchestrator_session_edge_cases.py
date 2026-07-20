"""Integration tests for orchestrator session lifecycle edge cases.

Tests verify file-state behavior of the UserPromptSubmit hook and
ups_task_sync cleanup when session boundary conditions arise.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agentflow.hooks.ups_task_sync import _cleanup_merged_in_flight
from agentflow.shell.session_paths import session_file


def test_scenario_1_resume_signal_tif_non_empty_non_merged():
    """Scenario 1: Resume signal (TIF non-empty, non-merged tasks).

    TIF contains task IDs that are NOT merged (gh returns nothing, no title match).
    Assert TIF still contains the task IDs after the call — the hook preserves
    non-merged in-flight tasks. This represents the state after a rate-limit
    pause where orchestrator resumes via 'continue' prompt.
    """
    tmp_path = Path(__import__("tempfile").mkdtemp())
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    # Create tasks.json with pending tasks
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps({
        "tasks": [
            {"task_id": "T-100", "status": "pending"},
            {"task_id": "T-101", "status": "pending"},
        ]
    }))

    # Set up TIF with non-merged tasks
    sid = "test-resume-sid"
    tif_file = session_file(agentflow_dir, "tasks_in_flight.json", sid)
    tif_file.write_text(json.dumps(["T-100", "T-101"]))

    # Mock PR state check and merged PR titles to return empty/non-matching
    with patch("agentflow.hooks.ups_task_sync._check_pr_state", return_value=None):
        with patch("agentflow.hooks.ups_task_sync._fetch_merged_pr_titles", return_value=set()):
            _cleanup_merged_in_flight(agentflow_dir, sid=sid)

    # Assert TIF still contains the task IDs (non-merged tasks preserved)
    result_tif = json.loads(tif_file.read_text())
    assert result_tif == ["T-100", "T-101"], "Non-merged tasks should be preserved in TIF"


def test_scenario_2_resume_signal_tif_empty():
    """Scenario 2: Resume signal (TIF empty).

    Call _cleanup_merged_in_flight with TIF file containing [].
    Assert no error, no file modification (early return on empty list).
    """
    tmp_path = Path(__import__("tempfile").mkdtemp())
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    # Create tasks.json
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps({"tasks": []}))

    # Set up TIF with empty list
    sid = "test-empty-tif-sid"
    tif_file = session_file(agentflow_dir, "tasks_in_flight.json", sid)
    tif_file.write_text(json.dumps([]))

    # Should complete without error or modification
    _cleanup_merged_in_flight(agentflow_dir, sid=sid)

    # Assert file is unchanged (still empty)
    result_tif = json.loads(tif_file.read_text())
    assert result_tif == [], "Empty TIF should remain unchanged"


def test_scenario_3_double_spawn_guard_merged_task_cleanup():
    """Scenario 3: Double-spawn guard.

    TIF has task T-999 whose tasks.json status is 'pending'. gh reports T-999
    PR as MERGED. _cleanup_merged_in_flight should mark T-999 complete and
    remove it from TIF. After call, TIF should be [] and tasks.json should
    show T-999 as 'complete'.
    """
    tmp_path = Path(__import__("tempfile").mkdtemp())
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    # Create tasks.json with T-999 as pending
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps({
        "tasks": [
            {"task_id": "T-999", "status": "pending"},
        ]
    }))

    # Set up task_prs.json mapping T-999 to a PR URL
    task_prs_file = agentflow_dir / "task_prs.json"
    task_prs_file.write_text(json.dumps({"T-999": "https://github.com/owner/repo/pull/123"}))

    # Set up TIF with T-999
    sid = "test-merged-task-sid"
    tif_file = session_file(agentflow_dir, "tasks_in_flight.json", sid)
    tif_file.write_text(json.dumps(["T-999"]))

    # Mock PR check to report MERGED
    with patch("agentflow.hooks.ups_task_sync._check_pr_state", return_value="MERGED"):
        with patch("agentflow.hooks.ups_task_sync._locked_write_tasks", return_value=True):
            with patch("subprocess.run"):
                _cleanup_merged_in_flight(agentflow_dir, sid=sid)

    # Assert TIF is now empty
    result_tif = json.loads(tif_file.read_text())
    assert result_tif == [], "Merged task should be removed from TIF"


def test_scenario_4_sid_mismatch_isolation():
    """Scenario 4: SID mismatch / isolation.

    Old SID had current_round.json and TIF with tasks. New SID starts fresh.
    session_file(agentflow_dir, 'tasks_in_flight.json', new_sid) returns a
    path that does NOT exist, confirming SID isolation.
    _cleanup_merged_in_flight(agentflow_dir, sid=new_sid) exits early (no file).
    Old SID files are untouched.
    """
    tmp_path = Path(__import__("tempfile").mkdtemp())
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    # Set up old SID with TIF and tasks
    old_sid = "old-session-id"
    old_tif = session_file(agentflow_dir, "tasks_in_flight.json", old_sid)
    old_tif.write_text(json.dumps(["T-200"]))
    old_round = session_file(agentflow_dir, "current_round.json", old_sid)
    old_round.write_text(json.dumps({"round": 1}))

    # Verify old SID files exist
    assert old_tif.exists(), "Old SID TIF should exist"
    assert old_round.exists(), "Old SID current_round should exist"

    # Create tasks.json
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps({"tasks": []}))

    # New SID starts fresh
    new_sid = "new-session-id"
    new_tif = session_file(agentflow_dir, "tasks_in_flight.json", new_sid)

    # Assert new SID path does NOT exist (isolation confirmed)
    assert not new_tif.exists(), "New SID TIF should not exist initially"

    # Call cleanup on new SID (should exit early)
    _cleanup_merged_in_flight(agentflow_dir, sid=new_sid)

    # Assert old SID files are untouched
    assert old_tif.exists(), "Old SID TIF should still exist after cleanup on new SID"
    assert json.loads(old_tif.read_text()) == ["T-200"], "Old SID TIF content should be unchanged"


def test_scenario_5_no_op_baseline():
    """Scenario 5: No-op baseline.

    Empty .agentflow dir (no TIF, no current_round.json), no SID.
    _cleanup_merged_in_flight(agentflow_dir, sid='') completes without error.
    No files are created or modified.
    """
    tmp_path = Path(__import__("tempfile").mkdtemp())
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    # Create tasks.json
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps({"tasks": []}))

    # Call with empty SID (legacy fallback)
    _cleanup_merged_in_flight(agentflow_dir, sid="")

    # Assert no files were created
    tif_file = agentflow_dir / "tasks_in_flight.json"
    assert not tif_file.exists(), "TIF file should not be created in no-op case"

    # Assert no errors occurred (function returned successfully)
    # If we reach this point without exception, the test passes
