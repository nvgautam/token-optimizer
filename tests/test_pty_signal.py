"""Tests for agentflow/shell/pty_signal.py — task_done tombstone behavior."""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path

import pytest


def _task_done(task_id: str, workspace: Path) -> None:
    from agentflow.shell.pty_signal import task_done
    task_done(task_id, workspace_root=workspace)


def test_task_done_writes_tombstone_when_last_task_drained(tmp_path, monkeypatch):
    tif = tmp_path / ".agentflow" / "tasks_in_flight.json"
    tif.parent.mkdir(parents=True)
    tif.write_text('["T-001"]')

    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
    _task_done("T-001", tmp_path)

    assert tif.exists(), "tasks_in_flight.json must remain as tombstone"
    assert json.loads(tif.read_text()) == []


def test_task_done_tombstone_not_deleted_when_already_empty(tmp_path):
    tif = tmp_path / ".agentflow" / "tasks_in_flight.json"
    tif.parent.mkdir(parents=True)
    tif.write_text("[]")

    _task_done("T-001", tmp_path)  # task not in list — idempotent

    assert tif.exists()
    assert json.loads(tif.read_text()) == []


def test_task_done_removes_task_from_multi_task_list(tmp_path, monkeypatch):
    tif = tmp_path / ".agentflow" / "tasks_in_flight.json"
    tif.parent.mkdir(parents=True)
    tif.write_text('["T-001", "T-002"]')

    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
    _task_done("T-001", tmp_path)

    data = json.loads(tif.read_text())
    assert "T-001" not in data
    assert "T-002" in data


def test_task_done_writes_task_complete_json_when_drained(tmp_path, monkeypatch):
    tif = tmp_path / ".agentflow" / "tasks_in_flight.json"
    tif.parent.mkdir(parents=True)
    tif.write_text('["T-001"]')

    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
    _task_done("T-001", tmp_path)

    complete = tmp_path / ".agentflow" / "task_complete.json"
    assert complete.exists()
    assert json.loads(complete.read_text())["status"] == "complete"


def test_task_done_no_task_complete_written_when_tasks_remain(tmp_path):
    tif = tmp_path / ".agentflow" / "tasks_in_flight.json"
    tif.parent.mkdir(parents=True)
    tif.write_text('["T-001", "T-002"]')

    _task_done("T-001", tmp_path)

    assert not (tmp_path / ".agentflow" / "task_complete.json").exists()


def test_task_start_sid_scoped_path(tmp_path, monkeypatch):
    """When AGENTFLOW_SESSION_ID is set, task_start writes to sessions/<SID>/tasks_in_flight.json"""
    from agentflow.shell.pty_signal import task_start

    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "test-session-123")
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    task_start("T-001", workspace_root=tmp_path)

    # Check SID-scoped path
    sid_path = agentflow_dir / "sessions" / "test-session-123" / "tasks_in_flight.json"
    assert sid_path.exists(), f"Expected {sid_path} to exist"
    assert json.loads(sid_path.read_text()) == ["T-001"]

    # Ensure flat path was NOT created
    flat_path = agentflow_dir / "tasks_in_flight.json"
    assert not flat_path.exists(), "Root-level tasks_in_flight.json should not exist when SID is set"


def test_task_done_sid_scoped_path(tmp_path, monkeypatch):
    """When AGENTFLOW_SESSION_ID is set, task_done reads/writes to sessions/<SID>/tasks_in_flight.json"""
    from agentflow.shell.pty_signal import task_done

    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "test-session-456")
    agentflow_dir = tmp_path / ".agentflow"
    sid_dir = agentflow_dir / "sessions" / "test-session-456"
    sid_dir.mkdir(parents=True, exist_ok=True)

    # Setup SID-scoped file
    tif_sid = sid_dir / "tasks_in_flight.json"
    tif_sid.write_text('["T-001"]')

    task_done("T-001", workspace_root=tmp_path)

    # Check that SID-scoped file was updated (not flat path)
    assert tif_sid.exists()
    assert json.loads(tif_sid.read_text()) == []

    # Check task_complete was also SID-scoped
    complete_sid = sid_dir / "task_complete.json"
    assert complete_sid.exists()
    assert json.loads(complete_sid.read_text())["status"] == "complete"


def test_task_done_fallback_flat_path_when_no_sid(tmp_path, monkeypatch):
    """When AGENTFLOW_SESSION_ID is empty, task_done uses flat path (backward compat)"""
    from agentflow.shell.pty_signal import task_done

    # Ensure no SID in env
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)

    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    # Use flat path
    flat_tif = agentflow_dir / "tasks_in_flight.json"
    flat_tif.write_text('["T-001"]')

    task_done("T-001", workspace_root=tmp_path)

    # Should still use flat path when no SID
    assert flat_tif.exists()
    assert json.loads(flat_tif.read_text()) == []
