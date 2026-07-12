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


def test_task_done_writes_tombstone_when_last_task_drained(tmp_path):
    tif = tmp_path / ".agentflow" / "tasks_in_flight.json"
    tif.parent.mkdir(parents=True)
    tif.write_text('["T-001"]')

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


def test_task_done_removes_task_from_multi_task_list(tmp_path):
    tif = tmp_path / ".agentflow" / "tasks_in_flight.json"
    tif.parent.mkdir(parents=True)
    tif.write_text('["T-001", "T-002"]')

    _task_done("T-001", tmp_path)

    data = json.loads(tif.read_text())
    assert "T-001" not in data
    assert "T-002" in data


def test_task_done_writes_task_complete_json_when_drained(tmp_path):
    tif = tmp_path / ".agentflow" / "tasks_in_flight.json"
    tif.parent.mkdir(parents=True)
    tif.write_text('["T-001"]')

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
