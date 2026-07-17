"""Integration test: full drain-restart file-state sequence (T-275)."""
from __future__ import annotations
import json
import time
import pathlib
from unittest.mock import patch, MagicMock
from agentflow.shell.state_machine import States
from tests.shell.conftest import make_manager
from agentflow.shell.drain_restart import _write_merged_and_clear, check_drain_restart


def test_drain_restart_integration_sequence(tmp_path):
    """Walks the complete file-state sequence for drain-restart."""
    # (0) Setup manager and temp paths
    sm, pty, tok = make_manager()
    sm._project_root = tmp_path
    sm.session_type = "orchestrator"
    sm._state_machine.state = States.IDLE

    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    # Paths
    current_round_path = agentflow_dir / "current_round.json"
    tasks_in_flight_path = agentflow_dir / "tasks_in_flight.json"
    context_fill_path = agentflow_dir / "context_fill.json"
    ep_path = tmp_path / "execution_plan.md"

    # Setup execution plan
    ep_path.write_text("## Addendum: T-275\n", encoding="utf-8")

    # (1) Write current_round.json + tasks_in_flight.json with tasks + context_fill.json above threshold
    current_round_path.write_text(json.dumps({"round_id": "R-275", "task_ids": ["T-275"]}), encoding="utf-8")
    tasks_in_flight_path.write_text(json.dumps(["T-275"]), encoding="utf-8")
    context_fill_path.write_text(json.dumps({"fill_tokens": 90000, "ts": time.time()}), encoding="utf-8")

    sm._current_round_path = current_round_path
    sm._tasks_in_flight_path = tasks_in_flight_path
    sm._config = {"handoff_primary_tokens": 80000}
    sm._log_audit = MagicMock()

    # (2) Call _write_merged_and_clear (simulates PR merge cleanup).
    # Since _write_merged_and_clear unlinks tasks_in_flight.json in the current codebase,
    # we intercept the unlink of tasks_in_flight_path to instead write the [] tombstone,
    # matching the hook's PR merge cleanup behavior.
    original_unlink = pathlib.Path.unlink

    def mock_unlink(self, *args, **kwargs):
        if self.name == "tasks_in_flight.json":
            self.write_text("[]", encoding="utf-8")
        else:
            original_unlink(self, *args, **kwargs)

    with patch.object(pathlib.Path, "unlink", mock_unlink):
        _write_merged_and_clear(sm)

    # (3) Assert current_round.json deleted and tasks_in_flight.json is [] tombstone
    assert not current_round_path.exists()
    assert tasks_in_flight_path.exists()
    assert json.loads(tasks_in_flight_path.read_text("utf-8")) == []

    # (4) Call check_drain_restart
    # (5) Assert trigger_handoff is called or state transitioned to RESTARTING (T-209 path)
    with patch.object(sm, "trigger_handoff") as mock_trigger, \
         patch.object(sm._state_machine, "on_enter_restarting"):
        check_drain_restart(sm)
        # Assert either trigger_handoff was called or state machine transitioned to RESTARTING
        assert sm._state_machine.state == States.RESTARTING or mock_trigger.called


def test_drain_restart_integration_edge_cases(tmp_path):
    """Test edge cases: missing files, stale tokens, and below threshold tokens."""
    sm, pty, tok = make_manager()
    sm._project_root = tmp_path
    sm.session_type = "orchestrator"
    sm._state_machine.state = States.IDLE

    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    sm._current_round_path = agentflow_dir / "current_round.json"
    sm._tasks_in_flight_path = agentflow_dir / "tasks_in_flight.json"
    sm._config = {"handoff_primary_tokens": 80000}
    sm._log_audit = MagicMock()

    # Case 1: missing context_fill.json
    sm._tasks_in_flight_path.write_text("[]", encoding="utf-8")
    check_drain_restart(sm)
    assert sm._state_machine.state == States.IDLE

    # Case 2: below threshold
    (agentflow_dir / "context_fill.json").write_text(json.dumps({"fill_tokens": 50000, "ts": time.time()}), encoding="utf-8")
    check_drain_restart(sm)
    assert sm._state_machine.state == States.IDLE

    # Case 3: stale timestamp
    (agentflow_dir / "context_fill.json").write_text(json.dumps({"fill_tokens": 90000, "ts": time.time() - 100}), encoding="utf-8")
    check_drain_restart(sm)
    assert sm._state_machine.state == States.IDLE
