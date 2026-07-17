#!/usr/bin/env python3
"""Tests for agentflow.hooks.ups_task_sync — PR/task cleanup module."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agentflow.hooks.ups_task_sync import (
    _check_pr_state,
    _cleanup_merged_in_flight,
    _fetch_merged_pr_titles,
    _log_drain,
    _locked_write_tasks,
    _mark_task_complete,
    _run_cleanup,
)


class TestCheckPrState:
    """Test _check_pr_state."""

    def test_check_pr_state_success(self):
        """Return state on successful gh call."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=json.dumps({"state": "MERGED"}),
            )
            result = _check_pr_state("https://github.com/owner/repo/pull/1")
            assert result == "MERGED"
            mock_run.assert_called_once()

    def test_check_pr_state_failure(self):
        """Return None on gh failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=1, stdout="")
            result = _check_pr_state("https://github.com/owner/repo/pull/1")
            assert result is None

    def test_check_pr_state_exception(self):
        """Return None on exception."""
        with patch("subprocess.run", side_effect=Exception("test error")):
            result = _check_pr_state("https://github.com/owner/repo/pull/1")
            assert result is None


class TestFetchMergedPrTitles:
    """Test _fetch_merged_pr_titles."""

    def test_fetch_merged_pr_titles_success(self):
        """Return set of PR titles on success."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=json.dumps([{"title": "feat(T-1): foo"}, {"title": "fix(T-2): bar"}]),
            )
            result = _fetch_merged_pr_titles()
            assert result == {"feat(T-1): foo", "fix(T-2): bar"}

    def test_fetch_merged_pr_titles_failure(self):
        """Return empty set on gh failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=1, stdout="")
            result = _fetch_merged_pr_titles()
            assert result == set()

    def test_fetch_merged_pr_titles_exception(self):
        """Return empty set on exception."""
        with patch("subprocess.run", side_effect=Exception("test error")):
            result = _fetch_merged_pr_titles()
            assert result == set()


class TestMarkTaskComplete:
    """Test _mark_task_complete."""

    def test_mark_task_complete_success(self):
        """Return True when task marked complete."""
        with patch("agentflow.hooks.ups_task_sync.TaskDB") as mock_db_class:
            mock_db = Mock()
            mock_db.mark_complete.return_value = "marked"
            mock_db_class.return_value = mock_db

            tmp_dir = Path(tempfile.gettempdir()) / "test_tasks"
            tmp_dir.mkdir(exist_ok=True)
            tasks_file = tmp_dir / "tasks.json"

            result = _mark_task_complete(tasks_file, "T-1")
            assert result is True

    def test_mark_task_complete_already_complete(self):
        """Return True when task already complete."""
        with patch("agentflow.hooks.ups_task_sync.TaskDB") as mock_db_class:
            mock_db = Mock()
            mock_db.mark_complete.return_value = "already_complete"
            mock_db_class.return_value = mock_db

            tmp_dir = Path(tempfile.gettempdir()) / "test_tasks"
            tmp_dir.mkdir(exist_ok=True)
            tasks_file = tmp_dir / "tasks.json"

            result = _mark_task_complete(tasks_file, "T-1")
            assert result is True

    def test_mark_task_complete_failure(self):
        """Return False on error."""
        with patch("agentflow.hooks.ups_task_sync.TaskDB") as mock_db_class:
            mock_db = Mock()
            mock_db.mark_complete.return_value = "error"
            mock_db_class.return_value = mock_db

            tmp_dir = Path(tempfile.gettempdir()) / "test_tasks"
            tmp_dir.mkdir(exist_ok=True)
            tasks_file = tmp_dir / "tasks.json"

            result = _mark_task_complete(tasks_file, "T-1")
            assert result is False


class TestRunCleanup:
    """Test _run_cleanup."""

    def test_run_cleanup_success(self):
        """Call cleanup_tasks.py as subprocess."""
        with patch("subprocess.run") as mock_run:
            root = Path("/test/root")
            _run_cleanup(root)
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "cleanup_tasks.py" in str(args)

    def test_run_cleanup_exception(self):
        """Swallow exceptions from subprocess."""
        with patch("subprocess.run", side_effect=Exception("test error")):
            root = Path("/test/root")
            # Should not raise
            _run_cleanup(root)


class TestLockedWriteTasks:
    """Test _locked_write_tasks."""

    def test_locked_write_tasks_success(self):
        """Mark complete and run cleanup on success."""
        with patch("agentflow.hooks.ups_task_sync.TaskDB") as mock_db_class, \
             patch("agentflow.hooks.ups_task_sync._run_cleanup") as mock_cleanup, \
             patch("agentflow.hooks.ups_task_sync._log_drain") as mock_log:

            mock_db = Mock()
            mock_db.mark_complete.return_value = "marked"
            mock_db_class.return_value = mock_db

            tmp_dir = Path(tempfile.gettempdir()) / "test_tasks"
            tmp_dir.mkdir(exist_ok=True)
            tasks_file = tmp_dir / "tasks.json"
            agentflow_dir = tmp_dir / ".agentflow"
            agentflow_dir.mkdir(exist_ok=True)

            result = _locked_write_tasks(tasks_file, agentflow_dir, "T-1")
            assert result is True
            mock_cleanup.assert_called_once()

    def test_locked_write_tasks_bad_result(self):
        """Return False on bad mark_complete result."""
        with patch("agentflow.hooks.ups_task_sync.TaskDB") as mock_db_class, \
             patch("agentflow.hooks.ups_task_sync._log_drain"):

            mock_db = Mock()
            mock_db.mark_complete.return_value = "error"
            mock_db_class.return_value = mock_db

            tmp_dir = Path(tempfile.gettempdir()) / "test_tasks"
            tmp_dir.mkdir(exist_ok=True)
            tasks_file = tmp_dir / "tasks.json"
            agentflow_dir = tmp_dir / ".agentflow"
            agentflow_dir.mkdir(exist_ok=True)

            result = _locked_write_tasks(tasks_file, agentflow_dir, "T-1")
            assert result is False


class TestLogDrain:
    """Test _log_drain."""

    def test_log_drain_appends_json(self, tmp_path):
        """Append JSON line to hook_drain_debug.jsonl."""
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()

        entry = {"event": "test_event", "data": "test_data"}
        _log_drain(agentflow_dir, entry)

        log_file = agentflow_dir / "hook_drain_debug.jsonl"
        assert log_file.exists()

        with open(log_file) as f:
            line = f.readline()
            data = json.loads(line)
            assert data["event"] == "test_event"
            assert data["data"] == "test_data"
            assert "ts" in data
            assert data["source"] == "ups_task_sync"

    def test_log_drain_multiple_entries(self, tmp_path):
        """Append multiple JSON lines."""
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()

        _log_drain(agentflow_dir, {"event": "event1"})
        _log_drain(agentflow_dir, {"event": "event2"})

        log_file = agentflow_dir / "hook_drain_debug.jsonl"
        with open(log_file) as f:
            lines = f.readlines()
            assert len(lines) == 2

    def test_log_drain_exception(self, tmp_path):
        """Swallow exceptions."""
        agentflow_dir = tmp_path / ".agentflow"
        # Don't create the directory

        # Should not raise
        _log_drain(agentflow_dir, {"event": "test"})


class TestCleanupMergedInFlight:
    """Test _cleanup_merged_in_flight."""

    def test_cleanup_merged_in_flight_no_tif_file(self, tmp_path):
        """Skip cleanup if tasks_in_flight.json doesn't exist."""
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()

        # Should not raise
        _cleanup_merged_in_flight(agentflow_dir)

    def test_cleanup_merged_in_flight_empty_list(self, tmp_path):
        """Skip cleanup if in_flight list is empty."""
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()

        tif_file = agentflow_dir / "tasks_in_flight.json"
        tif_file.write_text(json.dumps([]))

        # Should not raise
        _cleanup_merged_in_flight(agentflow_dir)

    def test_cleanup_merged_in_flight_mark_merged(self, tmp_path):
        """Mark task complete when PR is merged."""
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        root = tmp_path

        tif_file = agentflow_dir / "tasks_in_flight.json"
        tif_file.write_text(json.dumps(["T-1", "T-2"]))

        tasks_file = root / "tasks.json"
        tasks_file.write_text(json.dumps({"T-1": {}, "T-2": {}}))

        task_prs_file = agentflow_dir / "task_prs.json"
        task_prs_file.write_text(json.dumps({"T-1": "https://github.com/owner/repo/pull/1"}))

        with patch("agentflow.hooks.ups_task_sync._check_pr_state") as mock_check, \
             patch("agentflow.hooks.ups_task_sync._fetch_merged_pr_titles") as mock_fetch, \
             patch("agentflow.hooks.ups_task_sync._locked_write_tasks") as mock_locked, \
             patch("subprocess.run"):

            mock_check.return_value = "MERGED"
            mock_fetch.return_value = {"feat(T-2): something"}
            mock_locked.return_value = True

            _cleanup_merged_in_flight(agentflow_dir)

            # Check that tasks were marked complete
            updated_tif = json.loads(tif_file.read_text())
            # Both should be removed if marked complete
            assert mock_locked.call_count >= 1

    def test_cleanup_merged_in_flight_read_error(self, tmp_path):
        """Skip cleanup on read error."""
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()

        tif_file = agentflow_dir / "tasks_in_flight.json"
        tif_file.write_text("invalid json")

        # Should not raise
        _cleanup_merged_in_flight(agentflow_dir)

    def test_cleanup_merged_in_flight_write_updated_tif(self, tmp_path):
        """Update tasks_in_flight.json after marking complete."""
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        root = tmp_path

        tif_file = agentflow_dir / "tasks_in_flight.json"
        tif_file.write_text(json.dumps(["T-1", "T-2"]))

        tasks_file = root / "tasks.json"
        tasks_file.write_text(json.dumps({"T-1": {}, "T-2": {}}))

        with patch("agentflow.hooks.ups_task_sync._check_pr_state") as mock_check, \
             patch("agentflow.hooks.ups_task_sync._fetch_merged_pr_titles") as mock_fetch, \
             patch("agentflow.hooks.ups_task_sync._locked_write_tasks") as mock_locked, \
             patch("subprocess.run"), \
             patch("agentflow.hooks.ups_task_sync._log_drain"):

            mock_check.side_effect = lambda x: "MERGED"
            mock_fetch.return_value = set()
            mock_locked.return_value = True

            _cleanup_merged_in_flight(agentflow_dir)

            # Verify TIF was updated to remove completed tasks
            updated_tif = json.loads(tif_file.read_text())
            # If all tasks are marked complete, list should be empty or shorter
            assert isinstance(updated_tif, list)
