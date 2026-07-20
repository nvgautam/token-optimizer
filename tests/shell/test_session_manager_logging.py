"""Tests for logging and metrics in agentflow.shell.session_manager."""
from __future__ import annotations
import json
import pathlib
import sys
from unittest.mock import patch
import pytest

# Make conftest importable
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from conftest import make_manager, fire_output


def test_task_token_bracketing_logs(tmp_path):
    (tmp_path / ".agentflow").mkdir()
    (tmp_path / ".agentflow" / "current_round.json").write_text(json.dumps({
        "estimated_lines_per_task": {"T-067": 45}, "file_counts_per_task": {"T-067": 2}
    }), encoding="utf-8")
    sm, pty, tok = make_manager()
    sm.session_type = "orchestrator"
    (tmp_path / "home").mkdir()
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path), patch.object(pathlib.Path, "home", return_value=tmp_path / "home"):
        tok.accumulate("init", "claude")
        fire_output(sm, pty, "AGENTFLOW_TASK_START:T-067")
        assert sm._task_start_tokens.get("T-067") == 2
        tok.accumulate("worker work", "claude")
        tok.accumulate("more work", "claude")
        fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-067")
        log_file = tmp_path / "home" / ".agentflow" / "task_token_log.jsonl"
        assert log_file.exists()
        record = json.loads(log_file.read_text(encoding="utf-8").strip().split("\n")[0])
        assert record["task_id"] == "T-067" and record["token_delta"] == 3
        assert record["estimated_lines"] == 45 and record["file_count"] == 2

def test_session_manager_arm_reread(tmp_path):
    (tmp_path / ".agentflow").mkdir()
    arm_file = tmp_path / ".agentflow" / "verbosity_ab_arm.txt"
    arm_file.write_text("initial_arm", encoding="utf-8")
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, pty, _ = make_manager()
        assert sm._arm == "initial_arm"
        # First task completion -> turn_count becomes 1
        fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-001\n")
        assert sm._arm == "initial_arm"
        
        # Write new arm
        arm_file.write_text("new_arm", encoding="utf-8")
        
        # Trigger /clear via clear_signal file
        (tmp_path / ".agentflow" / "clear_signal").touch()
        fire_output(sm, pty, "some clear output\n")
        assert sm._turn_count == 0
        
        # Next task completion -> turn_count becomes 1 again, triggering re-read
        fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-002\n")
        assert sm._arm == "new_arm"
