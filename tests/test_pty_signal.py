"""Tests for agentflow/shell/pty_signal.py — task_done tombstone behavior."""
from __future__ import annotations
import json
from pathlib import Path



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
    """task_complete.json is eliminated — only tif tombstone [] signals completion."""
    tif = tmp_path / ".agentflow" / "tasks_in_flight.json"
    tif.parent.mkdir(parents=True)
    tif.write_text('["T-001"]')

    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
    _task_done("T-001", tmp_path)

    # task_complete.json is no longer written; poll_session watches tif==[] instead.
    complete = tmp_path / ".agentflow" / "task_complete.json"
    assert not complete.exists(), "task_complete.json must not be written (T-342)"
    assert tif.exists() and json.loads(tif.read_text()) == []


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

    # task_complete.json is no longer written (T-342); only tif tombstone [] signals completion.
    complete_sid = sid_dir / "task_complete.json"
    assert not complete_sid.exists(), "task_complete.json must not be written (T-342)"


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


def test_task_start_audit_contains_sid(tmp_path, monkeypatch):
    from agentflow.shell.pty_signal import task_start
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True)
    
    # 1. With explicit SID in environment
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "session-start-123")
    task_start("T-001", workspace_root=tmp_path)
    
    audit_file = agentflow_dir / "pty_audit.jsonl"
    assert audit_file.exists()
    entries = [json.loads(line) for line in audit_file.read_text().splitlines() if line.strip()]
    assert len(entries) == 1
    assert entries[0]["sid"] == "session-start-123"

    # 2. Defaulting when SID is not set
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
    task_start("T-002", workspace_root=tmp_path)
    
    entries = [json.loads(line) for line in audit_file.read_text().splitlines() if line.strip()]
    assert len(entries) == 2
    assert entries[1]["sid"] == ""


def test_task_done_audit_contains_sid(tmp_path, monkeypatch):
    from agentflow.shell.pty_signal import task_start, task_done
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True)
    
    # Pre-populate tasks in flight
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "session-done-123")
    task_start("T-001", workspace_root=tmp_path)
    task_start("T-002", workspace_root=tmp_path)
    
    # Clear logs to focus on task_done
    audit_file = agentflow_dir / "pty_audit.jsonl"
    if audit_file.exists():
        audit_file.unlink()
        
    # 1. Explicit sid parameter
    task_done("T-001", workspace_root=tmp_path, sid="session-done-123")
    entries = [json.loads(line) for line in audit_file.read_text().splitlines() if line.strip()]
    assert len(entries) == 1
    assert entries[0]["sid"] == "session-done-123"
    
    # 2. Defaults to env when sid param not passed (task_done emits 1 event: tif_written)
    task_done("T-002", workspace_root=tmp_path)
    entries = [json.loads(line) for line in audit_file.read_text().splitlines() if line.strip()]
    # T-342: task_complete_written event removed; task_done emits only tif_written.
    assert len(entries) == 2
    assert entries[1]["sid"] == "session-done-123"

    # 3. Defaulting when sid param not passed and env is empty
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
    # Reset file and do task_start/task_done with empty env
    tif_file = agentflow_dir / "tasks_in_flight.json"
    if tif_file.exists():
        tif_file.unlink()
    if audit_file.exists():
        audit_file.unlink()

    task_start("T-003", workspace_root=tmp_path)
    task_done("T-003", workspace_root=tmp_path)
    entries = [json.loads(line) for line in audit_file.read_text().splitlines() if line.strip()]
    # T-342: task_start(1 tif_written) + task_done(1 tif_written) = 2 events.
    assert len(entries) == 2
    assert entries[0]["sid"] == ""
    assert entries[1]["sid"] == ""


def test_handoff_complete_audit_contains_sid(tmp_path, monkeypatch):
    from agentflow.shell.pty_signal import handoff_complete
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True)
    
    # 1. Explicit sid parameter
    handoff_complete(workspace_root=tmp_path, sid="session-handoff-123")
    audit_file = agentflow_dir / "pty_audit.jsonl"
    entries = [json.loads(line) for line in audit_file.read_text().splitlines() if line.strip()]
    assert len(entries) == 1
    assert entries[0]["sid"] == "session-handoff-123"
    
    # 2. Defaults to env when sid param not passed
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "session-handoff-env")
    handoff_complete(workspace_root=tmp_path)
    entries = [json.loads(line) for line in audit_file.read_text().splitlines() if line.strip()]
    assert len(entries) == 2
    assert entries[1]["sid"] == "session-handoff-env"
    
    # 3. Defaulting when sid param not passed and env is empty
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
    handoff_complete(workspace_root=tmp_path)
    entries = [json.loads(line) for line in audit_file.read_text().splitlines() if line.strip()]
    assert len(entries) == 3
    assert entries[2]["sid"] == ""
