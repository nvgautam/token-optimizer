import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from agentflow.shell.state_machine import StateMachine, States

class _StubManager:
    def __init__(self, project_root: Path, state: States, fill_tokens: int = 90000):
        agentflow_dir = project_root / ".agentflow"
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        
        self._state_machine = StateMachine(initial_state=state, threshold_tokens=80000)
        self._project_root = project_root
        self.session_type = "orchestrator"
        self._current_round_path = agentflow_dir / "current_round.json"
        self._handoff_complete_path = agentflow_dir / "handoff_complete.json"
        self._task_complete_path = agentflow_dir / "task_complete.json"
        self._config = {"handoff_primary_tokens": 80000, "restart_delay_seconds": 0}
        self._last_restart_ts = 0.0
        self._audit_calls = []
        self._last_current_round_mtime = 0.0
        self._pty = type('obj', (object,), {'_exited': False})()
        
    @property
    def _tasks_in_flight_path(self) -> Path:
        from agentflow.shell.session_paths import session_file
        sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
        return session_file(self._project_root / ".agentflow", "tasks_in_flight.json", sid)
        
    def _log_audit(self, entry: dict) -> None:
        self._audit_calls.append(entry)

def test_current_round_detected_poll_session_success(tmp_path, monkeypatch):
    """Test Gap 1: current_round.json detected logs success path."""
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "env-sid")
    mgr = _StubManager(tmp_path, States.IDLE)
    current_round_path = tmp_path / ".agentflow" / "current_round.json"
    current_round_path.write_text(
        json.dumps({
            "round_id": "R1",
            "session_id": "env-sid",
            "task_ids": ["T-1"]
        }), encoding="utf-8"
    )
    mgr._last_current_round_mtime = 0.0
    
    from agentflow.shell.handoff_handler import poll_session
    poll_session(mgr)
    
    events = [entry.get("event") for entry in mgr._audit_calls]
    assert "current_round_detected" in events
    entry = next(e for e in mgr._audit_calls if e.get("event") == "current_round_detected")
    assert entry.get("round_id") == "R1"
    assert "mtime" in entry

def test_current_round_unlinked_on_drain(tmp_path):
    """Test Gap 2: current_round.json unlinked is logged after deletion."""
    mgr = _StubManager(tmp_path, States.TASK_RUNNING)
    current_round_path = tmp_path / ".agentflow" / "current_round.json"
    current_round_path.write_text(
        json.dumps({
            "round_id": "R2",
            "task_ids": ["T-1"]
        }), encoding="utf-8"
    )
    
    from agentflow.shell.drain_restart import _write_merged_and_clear
    _write_merged_and_clear(mgr)
    
    events = [entry.get("event") for entry in mgr._audit_calls]
    assert "current_round_unlinked" in events
    entry = next(e for e in mgr._audit_calls if e.get("event") == "current_round_unlinked")
    assert entry.get("round_id") == "R2"

def test_drain_no_current_round_logged_on_exception(tmp_path):
    """Test Gap 3: drain_no_current_round is logged when current_round.json is missing/malformed."""
    mgr = _StubManager(tmp_path, States.TASK_RUNNING)
    if mgr._current_round_path.exists():
        mgr._current_round_path.unlink()
        
    from agentflow.shell.drain_restart import _write_merged_and_clear
    _write_merged_and_clear(mgr)
    
    events = [entry.get("event") for entry in mgr._audit_calls]
    assert "drain_no_current_round" in events
    entry = next(e for e in mgr._audit_calls if e.get("event") == "drain_no_current_round")
    assert "error" in entry

def test_signal_files_unlinked_on_enter_idle(tmp_path):
    """Test Gap 4 & 5: signal files unlinked are logged on enter_idle."""
    mgr = _StubManager(tmp_path, States.IDLE)
    
    mgr._task_complete_path.write_text("{}", encoding="utf-8")
    mgr._handoff_complete_path.write_text("{}", encoding="utf-8")
    
    from agentflow.shell.session_manager_handlers import clear_signal_files
    clear_signal_files(mgr)
    
    events = [entry.get("event") for entry in mgr._audit_calls]
    assert events.count("signal_file_unlinked") == 2
    
    files = [entry.get("file") for entry in mgr._audit_calls if entry.get("event") == "signal_file_unlinked"]
    assert "task_complete.json" in files
    assert "handoff_complete.json" in files

def test_context_fill_reset_logged_on_enter_idle(tmp_path, monkeypatch):
    """Test Gap 8: context_fill_reset is logged on enter_idle."""
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "sid-xyz")
    mgr = _StubManager(tmp_path, States.IDLE)
    
    from agentflow.shell.session_manager_handlers import clear_signal_files
    clear_signal_files(mgr)
    
    events = [entry.get("event") for entry in mgr._audit_calls]
    assert "context_fill_reset" in events
    entry = next(e for e in mgr._audit_calls if e.get("event") == "context_fill_reset")
    assert entry.get("sid") == "sid-xyz"

def test_signal_files_unlinked_by_ups_hook(tmp_path, monkeypatch):
    """Test Gap 6 & 7: signal files unlinked by UPS hook are logged."""
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "sid-ups")
    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)
    
    from agentflow.shell.session_paths import session_file
    tc = session_file(agentflow_dir, "task_complete.json", "sid-ups")
    hc = session_file(agentflow_dir, "handoff_complete.json", "sid-ups")
    tc.write_text("{}", encoding="utf-8")
    hc.write_text("{}", encoding="utf-8")
    
    with patch("sys.argv", ["user_prompt_submit.py", "/handoff"]):
        with patch("sys.stdin.isatty", return_value=True):
            with patch("sys.exit") as mock_exit:
                from agentflow.hooks.user_prompt_submit import main
                main()
                
    log_file = agentflow_dir / "hook_drain_debug.jsonl"
    assert log_file.exists()
    
    lines = log_file.read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines]
    unlinked_events = [e for e in events if e.get("event") == "signal_file_unlinked"]
    
    assert len(unlinked_events) == 2
    files = [e.get("file") for e in unlinked_events]
    assert "task_complete.json" in files
    assert "handoff_complete.json" in files
