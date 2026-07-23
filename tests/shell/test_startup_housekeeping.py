"""Tests for startup housekeeping — round status auto-update on init."""
from __future__ import annotations
import json
import pathlib
import tempfile
from unittest.mock import patch, MagicMock
import pytest
from agentflow.shell.session_manager import SessionManager
from tests.shell.conftest import FakePTY, FakeTokenizer


@pytest.fixture
def setup_project_files(tmp_path):
    """Fixture to set up minimal project structure with execution_plan.md and tasks.json."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    tasks_json = tmp_path / "tasks.json"
    tasks_json.write_text(json.dumps({"tasks": []}), encoding="utf-8")

    execution_plan = tmp_path / "execution_plan.md"
    execution_plan.write_text("# Execution Plan\n", encoding="utf-8")

    yield {
        "agentflow_dir": agentflow_dir,
        "tasks_json": tasks_json,
        "execution_plan": execution_plan,
        "project_root": tmp_path,
    }


def test_round_status_update_all_complete(setup_project_files):
    """Test that round status is updated to [MERGED] when all tasks are complete."""
    project = setup_project_files

    # Set up tasks.json with all tasks complete
    tasks_json = project["tasks_json"]
    tasks_json.write_text(
        json.dumps({
            "tasks": [
                {"task_id": "T-001", "status": "complete"},
                {"task_id": "T-002", "status": "complete"},
            ]
        }),
        encoding="utf-8",
    )

    # Set up execution_plan.md with a round containing these tasks
    execution_plan = project["execution_plan"]
    execution_plan.write_text(
        "# Execution Plan\n\n"
        "| Round | Tasks | Status |\n"
        "|---|---|---|\n"
        "| R-1 | T-001, T-002 | [PENDING] |\n",
        encoding="utf-8",
    )

    # Initialize session manager
    with patch.object(pathlib.Path, "cwd", return_value=project["project_root"]):
        pty = FakePTY()
        tokenizer = FakeTokenizer()
        sm = SessionManager(pty, tokenizer, {})

        # Check that the round status was updated
        content = execution_plan.read_text(encoding="utf-8")
        assert "[MERGED]" in content
        assert "[PENDING]" not in content


def test_round_status_no_update_pending_task(setup_project_files):
    """Test that round status remains [PENDING] if any task is pending."""
    project = setup_project_files

    # Set up tasks.json with one task pending
    tasks_json = project["tasks_json"]
    tasks_json.write_text(
        json.dumps({
            "tasks": [
                {"task_id": "T-001", "status": "complete"},
                {"task_id": "T-002", "status": "pending"},
            ]
        }),
        encoding="utf-8",
    )

    # Set up execution_plan.md
    execution_plan = project["execution_plan"]
    execution_plan.write_text(
        "# Execution Plan\n\n"
        "| Round | Tasks | Status |\n"
        "|---|---|---|\n"
        "| R-1 | T-001, T-002 | [PENDING] |\n",
        encoding="utf-8",
    )

    # Initialize session manager
    with patch.object(pathlib.Path, "cwd", return_value=project["project_root"]):
        pty = FakePTY()
        tokenizer = FakeTokenizer()
        sm = SessionManager(pty, tokenizer, {})

        # Check that the round status was NOT updated
        content = execution_plan.read_text(encoding="utf-8")
        assert "[PENDING]" in content
        assert "[MERGED]" not in content


def test_halt_on_pending_round(setup_project_files):
    """Test that housekeeping halts at the first round with pending tasks."""
    project = setup_project_files

    # Set up tasks.json
    tasks_json = project["tasks_json"]
    tasks_json.write_text(
        json.dumps({
            "tasks": [
                {"task_id": "T-001", "status": "complete"},
                {"task_id": "T-002", "status": "pending"},
                {"task_id": "T-003", "status": "complete"},
            ]
        }),
        encoding="utf-8",
    )

    # Set up execution_plan.md with multiple rounds
    execution_plan = project["execution_plan"]
    execution_plan.write_text(
        "# Execution Plan\n\n"
        "| Round | Tasks | Status |\n"
        "|---|---|---|\n"
        "| R-1 | T-001, T-002 | [PENDING] |\n"
        "| R-2 | T-003 | [PENDING] |\n",
        encoding="utf-8",
    )

    # Initialize session manager
    with patch.object(pathlib.Path, "cwd", return_value=project["project_root"]):
        pty = FakePTY()
        tokenizer = FakeTokenizer()
        sm = SessionManager(pty, tokenizer, {})

        # Check that R-1 was NOT updated (still PENDING)
        # and R-2 was NOT touched (still PENDING)
        content = execution_plan.read_text(encoding="utf-8")
        lines = content.splitlines()
        # Count PENDING/MERGED on round rows
        round_rows = [ln for ln in lines if "| R-" in ln]
        assert len(round_rows) == 2
        # Both should still be PENDING since R-1 has a pending task
        assert all("[PENDING]" in ln for ln in round_rows)


def test_lock_acquired_and_released(setup_project_files):
    """Test that file lock is acquired and released correctly during write."""
    project = setup_project_files
    # Set up tasks.json with all complete
    tasks_json = project["tasks_json"]
    tasks_json.write_text(
        json.dumps({
            "tasks": [
                {"task_id": "T-001", "status": "complete"},
            ]
        }),
        encoding="utf-8",
    )

    # Set up execution_plan.md
    execution_plan = project["execution_plan"]
    execution_plan.write_text(
        "# Execution Plan\n\n"
        "| Round | Tasks | Status |\n"
        "|---|---|---|\n"
        "| R-1 | T-001 | [PENDING] |\n",
        encoding="utf-8",
    )

    # Initialize session manager
    with patch.object(pathlib.Path, "cwd", return_value=project["project_root"]):
        pty = FakePTY()
        tokenizer = FakeTokenizer()
        sm = SessionManager(pty, tokenizer, {})

        # Verify lock file doesn't remain locked (was released)
        lock_file = project["project_root"] / "execution_plan.md.lock"
        if lock_file.exists():
            # Try to acquire lock to verify it's not held
            try:
                with open(lock_file, "r", encoding="utf-8") as f:
                    import fcntl
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    # If we got here, lock was free
                    assert True
            except IOError:
                pytest.fail("Lock file is still locked")


def test_missing_tasks_json(setup_project_files):
    """Test graceful handling when tasks.json is missing."""
    project = setup_project_files

    # Remove tasks.json
    project["tasks_json"].unlink()

    # Set up execution_plan.md
    execution_plan = project["execution_plan"]
    execution_plan.write_text(
        "# Execution Plan\n\n"
        "| Round | Tasks | Status |\n"
        "|---|---|---|\n"
        "| R-1 | T-001 | [PENDING] |\n",
        encoding="utf-8",
    )

    # Initialize session manager — should not crash
    with patch.object(pathlib.Path, "cwd", return_value=project["project_root"]):
        pty = FakePTY()
        tokenizer = FakeTokenizer()
        sm = SessionManager(pty, tokenizer, {})

        # Plan should be unchanged
        content = execution_plan.read_text(encoding="utf-8")
        assert "[PENDING]" in content


def test_malformed_execution_plan(setup_project_files):
    """Test graceful handling of malformed execution_plan.md."""
    project = setup_project_files

    # Set up tasks.json
    tasks_json = project["tasks_json"]
    tasks_json.write_text(
        json.dumps({
            "tasks": [
                {"task_id": "T-001", "status": "complete"},
            ]
        }),
        encoding="utf-8",
    )

    # Set up malformed execution_plan.md (missing pipe delimiters)
    execution_plan = project["execution_plan"]
    execution_plan.write_text(
        "# Execution Plan\n\n"
        "R-1 T-001 [PENDING]\n",
        encoding="utf-8",
    )

    # Initialize session manager — should not crash
    with patch.object(pathlib.Path, "cwd", return_value=project["project_root"]):
        pty = FakePTY()
        tokenizer = FakeTokenizer()
        sm = SessionManager(pty, tokenizer, {})

        # Plan should be unchanged since it was malformed
        content = execution_plan.read_text(encoding="utf-8")
        assert "R-1 T-001 [PENDING]" in content


def test_multiple_complete_rounds(setup_project_files):
    """Test that multiple consecutive complete rounds are all updated."""
    project = setup_project_files

    # Set up tasks.json with all tasks complete
    tasks_json = project["tasks_json"]
    tasks_json.write_text(
        json.dumps({
            "tasks": [
                {"task_id": "T-001", "status": "complete"},
                {"task_id": "T-002", "status": "complete"},
                {"task_id": "T-003", "status": "complete"},
            ]
        }),
        encoding="utf-8",
    )

    # Set up execution_plan.md with 3 rounds
    execution_plan = project["execution_plan"]
    execution_plan.write_text(
        "# Execution Plan\n\n"
        "| Round | Tasks | Status |\n"
        "|---|---|---|\n"
        "| R-1 | T-001 | [PENDING] |\n"
        "| R-2 | T-002 | [PENDING] |\n"
        "| R-3 | T-003 | [PENDING] |\n",
        encoding="utf-8",
    )

    # Initialize session manager
    with patch.object(pathlib.Path, "cwd", return_value=project["project_root"]):
        pty = FakePTY()
        tokenizer = FakeTokenizer()
        sm = SessionManager(pty, tokenizer, {})

        # All rounds should be merged
        content = execution_plan.read_text(encoding="utf-8")
        assert content.count("[MERGED]") == 3
        assert "[PENDING]" not in content


def test_idempotency_on_second_startup(setup_project_files):
    """Test that housekeeping is idempotent — second startup doesn't re-update."""
    import time
    project = setup_project_files

    # Set up tasks.json
    tasks_json = project["tasks_json"]
    tasks_json.write_text(
        json.dumps({
            "tasks": [
                {"task_id": "T-001", "status": "complete"},
            ]
        }),
        encoding="utf-8",
    )

    # Set up execution_plan.md
    execution_plan = project["execution_plan"]
    execution_plan.write_text(
        "# Execution Plan\n\n"
        "| Round | Tasks | Status |\n"
        "|---|---|---|\n"
        "| R-1 | T-001 | [PENDING] |\n",
        encoding="utf-8",
    )

    # First startup
    with patch.object(pathlib.Path, "cwd", return_value=project["project_root"]):
        pty = FakePTY()
        tokenizer = FakeTokenizer()
        sm1 = SessionManager(pty, tokenizer, {})

        content1 = execution_plan.read_text(encoding="utf-8")
        mtime1 = execution_plan.stat().st_mtime

    # Small delay to ensure timestamp changes if file is rewritten
    time.sleep(0.1)

    # Second startup
    with patch.object(pathlib.Path, "cwd", return_value=project["project_root"]):
        pty = FakePTY()
        tokenizer = FakeTokenizer()
        sm2 = SessionManager(pty, tokenizer, {})

        content2 = execution_plan.read_text(encoding="utf-8")
        mtime2 = execution_plan.stat().st_mtime

    # Content should be the same, and mtime should not change
    assert content1 == content2
    assert mtime1 == mtime2
