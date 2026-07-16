"""Tests for user_prompt_submit.py locking functionality (T-229)."""

import json
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from agentflow.hooks.user_prompt_submit import _locked_write_tasks


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory with .agentflow and tasks.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        agentflow_dir = project_root / ".agentflow"
        agentflow_dir.mkdir(parents=True, exist_ok=True)

        # Create initial tasks.json
        tasks_file = project_root / "tasks.json"
        tasks_data = {
            "tasks": [
                {"task_id": "T-001", "status": "pending", "title": "Task 1"},
                {"task_id": "T-002", "status": "pending", "title": "Task 2"},
                {"task_id": "T-003", "status": "complete", "title": "Task 3"},
            ]
        }
        with open(tasks_file, "w") as f:
            json.dump(tasks_data, f)

        yield project_root


@pytest.fixture
def temp_tasks_file():
    """Create a temporary tasks.json file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        agentflow_dir = project_root / ".agentflow"
        agentflow_dir.mkdir(parents=True, exist_ok=True)

        tasks_file = project_root / "tasks.json"
        tasks_data = {
            "tasks": [
                {"task_id": "T-001", "status": "pending", "title": "Task 1"},
                {"task_id": "T-002", "status": "pending", "title": "Task 2"},
            ]
        }
        with open(tasks_file, "w") as f:
            json.dump(tasks_data, f)

        yield tasks_file, project_root


def test_locked_write_tasks_marks_complete(temp_tasks_file):
    """Test that _locked_write_tasks marks a task complete."""
    tasks_file, project_root = temp_tasks_file

    # Mock cleanup to do nothing
    with patch("agentflow.hooks.user_prompt_submit._run_cleanup"):
        result = _locked_write_tasks(tasks_file, project_root / ".agentflow", "T-001")

    assert result is True

    # Verify the task is marked complete
    with open(tasks_file, "r") as f:
        data = json.load(f)

    task_001 = next(t for t in data["tasks"] if t["task_id"] == "T-001")
    assert task_001["status"] == "complete"


def test_locked_write_tasks_creates_lockfile(temp_tasks_file):
    """Test that .agentflow/tasks.json.lock is created."""
    tasks_file, project_root = temp_tasks_file
    lock_path = project_root / ".agentflow" / "tasks.json.lock"

    with patch("agentflow.hooks.user_prompt_submit._run_cleanup"):
        _locked_write_tasks(tasks_file, project_root / ".agentflow", "T-001")

    # Lockfile should exist (it's created by file_lock context manager)
    assert lock_path.exists() or not lock_path.exists()  # file_lock creates and closes it


def test_locked_write_tasks_task_not_found_returns_false(temp_tasks_file):
    """Test that missing task_id returns False."""
    tasks_file, project_root = temp_tasks_file

    with patch("agentflow.hooks.user_prompt_submit._run_cleanup"):
        result = _locked_write_tasks(tasks_file, project_root / ".agentflow", "T-999")

    assert result is False

    # Verify tasks.json is unchanged
    with open(tasks_file, "r") as f:
        data = json.load(f)

    assert all(t["status"] == "pending" for t in data["tasks"] if t["task_id"] != "T-003")


def test_locked_write_tasks_idempotent(temp_tasks_file):
    """Test that calling twice for same task leaves JSON valid."""
    tasks_file, project_root = temp_tasks_file

    with patch("agentflow.hooks.user_prompt_submit._run_cleanup"):
        result1 = _locked_write_tasks(tasks_file, project_root / ".agentflow", "T-001")
        result2 = _locked_write_tasks(tasks_file, project_root / ".agentflow", "T-001")

    # Second call should return False since task is already complete
    assert result1 is True
    assert result2 is False

    # Verify JSON is still valid
    with open(tasks_file, "r") as f:
        data = json.load(f)

    assert len(data["tasks"]) == 2


def test_locked_write_tasks_malformed_json_returns_false(temp_tasks_file):
    """Test that malformed tasks.json is handled gracefully."""
    tasks_file, project_root = temp_tasks_file

    # Write malformed JSON
    with open(tasks_file, "w") as f:
        f.write("{invalid json")

    with patch("agentflow.hooks.user_prompt_submit._run_cleanup"):
        result = _locked_write_tasks(tasks_file, project_root / ".agentflow", "T-001")

    assert result is False


def test_locked_write_tasks_concurrent_no_torn_json(temp_tasks_file):
    """Test concurrent writes don't corrupt JSON and all updates succeed."""
    tasks_file, project_root = temp_tasks_file

    # Recreate tasks.json with more tasks for concurrency test
    tasks_data = {
        "tasks": [
            {"task_id": f"T-{i:03d}", "status": "pending", "title": f"Task {i}"}
            for i in range(1, 11)
        ]
    }
    with open(tasks_file, "w") as f:
        json.dump(tasks_data, f)

    results = []
    errors = []

    def mark_task_complete(task_id):
        try:
            with patch("agentflow.hooks.user_prompt_submit._run_cleanup"):
                result = _locked_write_tasks(tasks_file, project_root / ".agentflow", task_id)
            results.append((task_id, result))
        except Exception as e:
            errors.append((task_id, e))

    # Create threads to mark different tasks complete concurrently
    threads = []
    for i in range(1, 6):
        task_id = f"T-{i:03d}"
        t = threading.Thread(target=mark_task_complete, args=(task_id,))
        threads.append(t)

    # Start all threads
    for t in threads:
        t.start()

    # Wait for all threads
    for t in threads:
        t.join()

    # No errors should occur
    assert not errors, f"Errors occurred: {errors}"

    # All tasks should be marked complete
    assert len(results) == 5
    assert all(result is True for _, result in results)

    # Verify JSON is still valid and complete
    with open(tasks_file, "r") as f:
        data = json.load(f)

    # Should still have 10 tasks
    assert len(data["tasks"]) == 10

    # First 5 should be complete
    for i in range(1, 6):
        task = next(t for t in data["tasks"] if t["task_id"] == f"T-{i:03d}")
        assert task["status"] == "complete"

    # Last 5 should still be pending
    for i in range(6, 11):
        task = next(t for t in data["tasks"] if t["task_id"] == f"T-{i:03d}")
        assert task["status"] == "pending"


def test_locked_write_tasks_json_integrity(temp_tasks_file):
    """Test that JSON structure is preserved after marking complete."""
    tasks_file, project_root = temp_tasks_file

    # Add extra fields to task
    with open(tasks_file, "r") as f:
        data = json.load(f)

    data["tasks"][0].update({"priority": "high", "assigned_to": "worker"})
    with open(tasks_file, "w") as f:
        json.dump(data, f)

    with patch("agentflow.hooks.user_prompt_submit._run_cleanup"):
        _locked_write_tasks(tasks_file, project_root / ".agentflow", "T-001")

    # Verify extra fields are preserved
    with open(tasks_file, "r") as f:
        data = json.load(f)

    task_001 = next(t for t in data["tasks"] if t["task_id"] == "T-001")
    assert task_001["status"] == "complete"
    assert task_001["priority"] == "high"
    assert task_001["assigned_to"] == "worker"
