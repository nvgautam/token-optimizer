"""Tests for session-scoped log observability (T-311)."""

import json
import os
import time
import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from agentflow.hooks.post_tool_use_agent import _log as post_tool_log
from agentflow.shell.pty_shell import ProxyShell


def test_hook_session_start_header_and_sid_injection(tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    
    # Mock OS environ for AGENTFLOW_SESSION_ID
    sid = "test-session-123"
    
    # Mock finding workspace root
    with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
        with patch.dict(os.environ, {"AGENTFLOW_SESSION_ID": sid}):
            # Set up session files to simulate active tasks
            from agentflow.shell.session_paths import session_file
            tif_file = session_file(agentflow_dir, "tasks_in_flight.json", sid)
            tif_file.write_text(json.dumps(["T-311"]))
            
            ss_file = session_file(agentflow_dir, "session_state.json", sid)
            ss_file.write_text(json.dumps({"session_type": "worker"}))
            
            # Log an event
            post_tool_log(agentflow_dir, {"event": "test_event", "foo": "bar"})
            
            # Read hook_drain_debug.jsonl
            log_file = agentflow_dir / "hook_drain_debug.jsonl"
            assert log_file.exists()
            
            lines = log_file.read_text().splitlines()
            assert len(lines) == 2
            
            # First line must be session-start header
            header = json.loads(lines[0])
            assert header["sid"] == sid
            assert header["session_type"] == "worker"
            assert header["task_ids"] == ["T-311"]
            assert "ts" in header
            
            # Second line must be the actual entry with sid injected
            entry = json.loads(lines[1])
            assert entry["sid"] == sid
            assert entry["event"] == "test_event"
            assert entry["foo"] == "bar"


def test_pty_audit_sid_injection_and_header(tmp_path):
    # Mock project root
    project_root = tmp_path
    agentflow_dir = project_root / ".agentflow"
    agentflow_dir.mkdir()
    
    sid = "pty-session-456"
    
    # Set up session state
    from agentflow.shell.session_paths import session_file
    tif_file = session_file(agentflow_dir, "tasks_in_flight.json", sid)
    tif_file.write_text(json.dumps(["T-100", "T-200"]))
    
    ss_file = session_file(agentflow_dir, "session_state.json", sid)
    ss_file.write_text(json.dumps({"session_type": "orchestrator"}))
    
    with patch.dict(os.environ, {"AGENTFLOW_SESSION_ID": sid}):
        # Mock SessionManager and verify monkey patches
        mock_pty = MagicMock()
        mock_tokenizer = MagicMock()
        
        # Import SessionManager to verify patched behavior
        from agentflow.shell.session_manager import SessionManager
        from agentflow.shell.session_audit import log_audit
        
        manager = SessionManager(mock_pty, mock_tokenizer, {})
        manager._project_root = project_root
        
        # Write an audit log entry
        log_audit(manager, {"event": "some_audit_event", "x": 42})
        
        audit_file = agentflow_dir / "pty_audit.jsonl"
        assert audit_file.exists()
        
        lines = audit_file.read_text().splitlines()
        assert len(lines) == 2
        
        # First entry: session-start header
        header = json.loads(lines[0])
        assert header["sid"] == sid
        assert header["session_type"] == "orchestrator"
        assert header["task_ids"] == ["T-100", "T-200"]
        assert "ts" in header
        
        # Second entry: actual log with sid
        entry = json.loads(lines[1])
        assert entry["sid"] == sid
        assert entry["event"] == "some_audit_event"
        assert entry["x"] == 42


def test_interleaved_sessions_isolation(tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    
    # Simulate two sessions writing to hook_drain_debug.jsonl
    with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
        # Session A
        with patch.dict(os.environ, {"AGENTFLOW_SESSION_ID": "sid-A"}):
            post_tool_log(agentflow_dir, {"event": "event_A1"})
            
        # Session B
        with patch.dict(os.environ, {"AGENTFLOW_SESSION_ID": "sid-B"}):
            post_tool_log(agentflow_dir, {"event": "event_B1"})
            
        # Session A again
        with patch.dict(os.environ, {"AGENTFLOW_SESSION_ID": "sid-A"}):
            post_tool_log(agentflow_dir, {"event": "event_A2"})
            
    # Read all lines and filter by sid
    log_file = agentflow_dir / "hook_drain_debug.jsonl"
    lines = [json.loads(line) for line in log_file.read_text().splitlines()]
    
    # Filter for A
    entries_A = [e for e in lines if e.get("sid") == "sid-A"]
    assert len(entries_A) == 3
    assert entries_A[0]["session_type"] == "worker"  # Header
    assert entries_A[1]["event"] == "event_A1"
    assert entries_A[2]["event"] == "event_A2"
    
    # Filter for B
    entries_B = [e for e in lines if e.get("sid") == "sid-B"]
    assert len(entries_B) == 2
    assert entries_B[0]["session_type"] == "worker"  # Header
    assert entries_B[1]["event"] == "event_B1"


def test_logs_subcommand(tmp_path, capsys):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    
    # Write some mock logs
    hd_file = agentflow_dir / "hook_drain_debug.jsonl"
    hd_file.write_text(
        json.dumps({"sid": "session-X", "event": "ev1", "ts": 1000.0}) + "\n" +
        json.dumps({"sid": "session-Y", "event": "ev2", "ts": 2000.0}) + "\n" +
        json.dumps({"sid": "session-X", "event": "ev3", "ts": 1500.0}) + "\n"
    )
    
    pa_file = agentflow_dir / "pty_audit.jsonl"
    pa_file.write_text(
        json.dumps({"sid": "session-X", "event": "pa1", "ts": "2026-07-21T12:00:00"}) + "\n"
    )
    
    # Import and run command logs
    from agentflow.cli import build_parser
    parser = build_parser()
    
    with patch("agentflow.hooks.post_tool_use_agent._find_workspace_root", return_value=tmp_path):
        args = parser.parse_args(["logs", "--session", "session-X"])
        
        from agentflow.cli import cmd_logs
        rc = cmd_logs(args)
        assert rc == 0
        
        captured = capsys.readouterr()
        lines = captured.out.splitlines()
        assert len(lines) == 3
        
        entries = [json.loads(line) for line in lines]
        # Should be sorted by timestamp
        assert entries[0]["event"] == "ev1"
        assert entries[1]["event"] == "ev3"
        assert entries[2]["event"] == "pa1"
