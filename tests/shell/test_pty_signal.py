import json
import sys
from pathlib import Path
import pytest

from agentflow.shell.pty_signal import (
    task_start,
    task_done,
    handoff_complete,
    find_workspace_root,
    main
)

def test_task_start_basic(tmp_path):
    tasks_file = tmp_path / "tasks.json"
    tasks_data = {
        "tasks": [
            {"task_id": "T-001", "status": "pending"},
            {"task_id": "T-002", "status": "pending"}
        ]
    }
    tasks_file.write_text(json.dumps(tasks_data))

    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    task_start("T-001", workspace_root=tmp_path)

    in_flight_file = agentflow_dir / "tasks_in_flight.json"
    assert in_flight_file.exists()
    
    with open(in_flight_file, "r") as f:
        in_flight = json.load(f)
    assert in_flight == ["T-001"]

def test_task_start_clears_stale(tmp_path):
    tasks_file = tmp_path / "tasks.json"
    tasks_data = {
        "tasks": [
            {"task_id": "T-001", "status": "pending"}
        ]
    }
    tasks_file.write_text(json.dumps(tasks_data))

    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    in_flight_file = agentflow_dir / "tasks_in_flight.json"
    in_flight_file.write_text(json.dumps(["T-999"]))

    task_start("T-001", workspace_root=tmp_path)

    with open(in_flight_file, "r") as f:
        in_flight = json.load(f)
    assert "T-999" not in in_flight
    assert "T-001" in in_flight
    assert in_flight == ["T-001"]

def test_task_done_parallel(tmp_path):
    tasks_file = tmp_path / "tasks.json"
    tasks_data = {
        "tasks": [
            {"task_id": "T-001", "status": "pending"},
            {"task_id": "T-002", "status": "pending"}
        ]
    }
    tasks_file.write_text(json.dumps(tasks_data))

    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    task_start("T-001", workspace_root=tmp_path)
    task_start("T-002", workspace_root=tmp_path)

    in_flight_file = agentflow_dir / "tasks_in_flight.json"
    complete_file = agentflow_dir / "task_complete.json"

    task_done("T-001", workspace_root=tmp_path)

    assert in_flight_file.exists()
    assert not complete_file.exists()
    with open(in_flight_file, "r") as f:
        assert json.load(f) == ["T-002"]

    task_done("T-002", workspace_root=tmp_path)

    assert not in_flight_file.exists()
    assert complete_file.exists()
    with open(complete_file, "r") as f:
        res = json.load(f)
        assert res.get("status") == "complete"

def test_handoff_complete_idempotent(tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    handoff_file = agentflow_dir / "handoff_complete.json"

    handoff_complete(workspace_root=tmp_path)
    assert handoff_file.exists()
    with open(handoff_file, "r") as f:
        assert json.load(f).get("status") == "complete"

    handoff_complete(workspace_root=tmp_path)
    assert handoff_file.exists()

def test_find_workspace_root_fallback(tmp_path, monkeypatch):
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    monkeypatch.setattr(Path, "cwd", lambda: empty_dir)
    root = find_workspace_root()
    assert root == empty_dir

def test_invalid_tasks_json_warning(tmp_path):
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text("invalid json")
    
    task_start("T-001", workspace_root=tmp_path)
    
    in_flight_file = tmp_path / ".agentflow" / "tasks_in_flight.json"
    assert in_flight_file.exists()

def test_invalid_tasks_in_flight_warning(tmp_path):
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-001"}]}))
    
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    in_flight_file = agentflow_dir / "tasks_in_flight.json"
    in_flight_file.write_text("invalid json")

    task_start("T-001", workspace_root=tmp_path)
    with open(in_flight_file, "r") as f:
        assert json.load(f) == ["T-001"]

def test_cli_task_start_success(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-001"}]}))

    monkeypatch.setattr(sys, "argv", ["pty_signal.py", "task_start", "T-001"])
    main()

    in_flight_file = tmp_path / ".agentflow" / "tasks_in_flight.json"
    assert in_flight_file.exists()
    with open(in_flight_file, "r") as f:
        assert json.load(f) == ["T-001"]

def test_cli_task_done_success(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-001"}]}))

    monkeypatch.setattr(sys, "argv", ["pty_signal.py", "task_start", "T-001"])
    main()

    monkeypatch.setattr(sys, "argv", ["pty_signal.py", "task_done", "T-001"])
    main()

    assert not (tmp_path / ".agentflow" / "tasks_in_flight.json").exists()
    assert (tmp_path / ".agentflow" / "task_complete.json").exists()

def test_cli_handoff_complete_success(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["pty_signal.py", "handoff_complete"])
    main()
    assert (tmp_path / ".agentflow" / "handoff_complete.json").exists()

def test_cli_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

    monkeypatch.setattr(sys, "argv", ["pty_signal.py"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1

    monkeypatch.setattr(sys, "argv", ["pty_signal.py", "task_start"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1

    monkeypatch.setattr(sys, "argv", ["pty_signal.py", "unknown_subcommand"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
