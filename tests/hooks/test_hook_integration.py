"""Integration tests for hook signal edge cases: missing SID, duplicate calls, concurrency, and corruption."""
import json
import os
import sys
import threading
import time
import io
from pathlib import Path
import pytest

from agentflow.shell.pty_signal import task_start, task_done, handoff_complete
from agentflow.hooks.post_tool_use_agent import main as post_tool_main
from agentflow.hooks.user_prompt_submit import main as ups_main


@pytest.fixture
def clean_workspace(tmp_path, monkeypatch):
    """Fixture to set up a clean agentflow directory structure and patch CWD to avoid touching real repo."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)
    
    # Write a dummy tasks.json
    tasks_file = tmp_path / "tasks.json"
    tasks_data = {
        "tasks": [
            {"task_id": "T-001", "status": "pending"},
            {"task_id": "T-002", "status": "pending"}
        ]
    }
    tasks_file.write_text(json.dumps(tasks_data))
    
    # Patch CWD to tmp_path so hooks find this workspace root
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    
    return tmp_path


def test_missing_session_id_graceful_no_op(clean_workspace, monkeypatch):
    """Missing AGENTFLOW_SESSION_ID env var: should graceful no-op or fallback.
    Verify that executing hooks or calling task_done/task_start does not crash
    and handles the missing environment variable gracefully.
    """
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
    
    # 1. Calling task_done should not crash
    try:
        task_done("T-001", workspace_root=clean_workspace)
    except Exception as e:
        pytest.fail(f"task_done crashed without SID: {e}")

    # 2. Calling task_start should not crash
    try:
        task_start("T-001", workspace_root=clean_workspace)
    except Exception as e:
        pytest.fail(f"task_start crashed without SID: {e}")

    # 3. Running hooks via main entrypoints should exit 0 and not crash
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    monkeypatch.setattr(sys, "argv", ["post_tool_use_agent.py"])
    
    try:
        with pytest.raises(SystemExit) as excinfo:
            post_tool_main()
        assert excinfo.value.code == 0
    except Exception as e:
        pytest.fail(f"post_tool_use_agent main crashed: {e}")

    monkeypatch.setattr(sys, "argv", ["user_prompt_submit.py", "/orchestrate"])
    try:
        with pytest.raises(SystemExit) as excinfo:
            ups_main()
        assert excinfo.value.code == 0
    except Exception as e:
        pytest.fail(f"user_prompt_submit main crashed: {e}")


def test_duplicate_task_done_idempotent(clean_workspace, monkeypatch):
    """Duplicate task_done calls: should be idempotent and not crash."""
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "test-dup-session")
    
    # Start tasks
    task_start("T-001", workspace_root=clean_workspace)
    task_start("T-002", workspace_root=clean_workspace)
    
    # Call task_done on T-001 first time
    task_done("T-001", workspace_root=clean_workspace)
    
    # Verify T-001 is removed
    sid_dir = clean_workspace / ".agentflow" / "sessions" / "test-dup-session"
    tif_file = sid_dir / "tasks_in_flight.json"
    assert json.loads(tif_file.read_text()) == ["T-002"]
    
    # Call task_done on T-001 second time (duplicate)
    try:
        task_done("T-001", workspace_root=clean_workspace)
    except Exception as e:
        pytest.fail(f"Duplicate task_done call crashed: {e}")
        
    # Verify no change and no crash
    assert json.loads(tif_file.read_text()) == ["T-002"]


def test_corrupt_tasks_in_flight_handling(clean_workspace, monkeypatch):
    """Corrupt tasks_in_flight.json (invalid JSON): should gracefully handle and reset safely without crash."""
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "test-corrupt-session")
    
    sid_dir = clean_workspace / ".agentflow" / "sessions" / "test-corrupt-session"
    sid_dir.mkdir(parents=True, exist_ok=True)
    tif_file = sid_dir / "tasks_in_flight.json"
    
    # 1. Write corrupt invalid JSON
    tif_file.write_text("{corrupt invalid json")
    
    # 2. Call task_start - should reset the file safely
    try:
        task_start("T-001", workspace_root=clean_workspace)
    except Exception as e:
        pytest.fail(f"task_start crashed with corrupt tasks_in_flight.json: {e}")
        
    assert json.loads(tif_file.read_text()) == ["T-001"]

    # 3. Write corrupt invalid JSON again
    tif_file.write_text("['unclosed bracket")
    
    # 4. Call task_done - should handle gracefully and reset safely without crashing
    try:
        task_done("T-001", workspace_root=clean_workspace)
    except Exception as e:
        pytest.fail(f"task_done crashed with corrupt tasks_in_flight.json: {e}")
        
    # The corrupted file should be safely reset (it is drained/empty)
    assert tif_file.exists()
    assert json.loads(tif_file.read_text()) == []


def test_concurrent_signal_writes(clean_workspace, monkeypatch):
    """Concurrent signal writes: should be last-write-wins with no corruption (using locking)."""
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "test-concurrent-session")
    
    sid_dir = clean_workspace / ".agentflow" / "sessions" / "test-concurrent-session"
    sid_dir.mkdir(parents=True, exist_ok=True)
    
    num_threads = 10
    threads = []
    errors = []
    
    def worker(task_idx):
        try:
            task_id = f"T-{task_idx:03d}"
            task_start(task_id, workspace_root=clean_workspace)
            time.sleep(0.01)
            task_done(task_id, workspace_root=clean_workspace)
        except Exception as e:
            errors.append(e)
            
    # Setup tasks in tasks.json
    tasks_file = clean_workspace / "tasks.json"
    tasks_data = {"tasks": [{"task_id": f"T-{i:03d}", "status": "pending"} for i in range(num_threads)]}
    tasks_file.write_text(json.dumps(tasks_data))

    for i in range(num_threads):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    assert not errors, f"Errors occurred during concurrent signal writes: {errors}"
    
    # Verify tasks_in_flight.json is not corrupted and is valid JSON
    tif_file = sid_dir / "tasks_in_flight.json"
    assert tif_file.exists()
    try:
        data = json.loads(tif_file.read_text())
        assert isinstance(data, list)
    except Exception as e:
        pytest.fail(f"tasks_in_flight.json was corrupted: {e}\nContent: {tif_file.read_text()}")
