"""Tests for check_drain_restart regression fix (T-274)."""
from __future__ import annotations
import json
import time
from unittest.mock import patch
from agentflow.shell.state_machine import States
from tests.shell.conftest import make_manager
from agentflow.shell.drain_restart import check_drain_restart


def test_drain_restart_t274_tif_tombstone_equivalent_to_round_present(tmp_path):
	"""Verify that when current_round.json is missing, but tasks_in_flight.json is [] (tombstone),
	drain restart still fires (T-274 fix).
	"""
	sm, pty, tok = make_manager()
	sm._project_root = tmp_path
	sm.session_type = "orchestrator"
	sm._state_machine.state = States.IDLE

	agentflow_dir = tmp_path / ".agentflow"
	agentflow_dir.mkdir()

	# current_round.json is ABSENT
	# context_fill.json exists with enough tokens
	(agentflow_dir / "context_fill.json").write_text(json.dumps({"fill_tokens": 90000, "ts": time.time()}))
	# tasks_in_flight.json exists and is empty []
	(agentflow_dir / "tasks_in_flight.json").write_text("[]")

	with patch.object(sm, "trigger_handoff") as mock_trigger, \
		 patch.object(sm._state_machine, "on_enter_restarting"):
		check_drain_restart(sm)
		mock_trigger.assert_not_called()

	assert sm._state_machine.state == States.RESTARTING


def test_drain_restart_t274_no_round_no_tombstone_skips(tmp_path):
	"""Verify that when current_round.json is missing, and tasks_in_flight.json is missing or non-empty,
	drain restart skips (T-274 fix).
	"""
	sm, pty, tok = make_manager()
	sm._project_root = tmp_path
	sm.session_type = "orchestrator"
	sm._state_machine.state = States.IDLE

	agentflow_dir = tmp_path / ".agentflow"
	agentflow_dir.mkdir()

	(agentflow_dir / "context_fill.json").write_text(json.dumps({"fill_tokens": 90000, "ts": time.time()}))

	# Case 1: TIF missing
	with patch.object(sm, "trigger_handoff") as mock_trigger:
		check_drain_restart(sm)
		mock_trigger.assert_not_called()
	assert sm._state_machine.state == States.IDLE

	# Case 2: TIF non-empty
	(agentflow_dir / "tasks_in_flight.json").write_text(json.dumps(["T-001"]))
	with patch.object(sm, "trigger_handoff") as mock_trigger:
		check_drain_restart(sm)
		mock_trigger.assert_not_called()
	assert sm._state_machine.state == States.IDLE


def test_drain_restart_t274_stale_fill_skips(tmp_path):
	"""Verify that when context fill ts is stale, drain restart skips."""
	sm, pty, tok = make_manager()
	sm._project_root = tmp_path
	sm.session_type = "orchestrator"
	sm._state_machine.state = States.IDLE

	agentflow_dir = tmp_path / ".agentflow"
	agentflow_dir.mkdir()

	# Stale timestamp (more than 60s ago)
	(agentflow_dir / "context_fill.json").write_text(json.dumps({"fill_tokens": 90000, "ts": time.time() - 100}))
	(agentflow_dir / "tasks_in_flight.json").write_text("[]")

	with patch.object(sm, "trigger_handoff") as mock_trigger:
		check_drain_restart(sm)
		mock_trigger.assert_not_called()
	assert sm._state_machine.state == States.IDLE


def test_drain_restart_t274_below_threshold_skips(tmp_path):
	"""Verify that when context fill is below threshold, drain restart skips."""
	sm, pty, tok = make_manager()
	sm._project_root = tmp_path
	sm.session_type = "orchestrator"
	sm._state_machine.state = States.IDLE

	agentflow_dir = tmp_path / ".agentflow"
	agentflow_dir.mkdir()

	(agentflow_dir / "context_fill.json").write_text(json.dumps({"fill_tokens": 50000, "ts": time.time()}))
	(agentflow_dir / "tasks_in_flight.json").write_text("[]")

	with patch.object(sm, "trigger_handoff") as mock_trigger:
		check_drain_restart(sm)
		mock_trigger.assert_not_called()
	assert sm._state_machine.state == States.IDLE


def test_drain_restart_t274_wrong_state_skips(tmp_path):
	"""Verify that when state is not IDLE or TASK_RUNNING, drain restart skips."""
	sm, pty, tok = make_manager()
	sm._project_root = tmp_path
	sm.session_type = "orchestrator"
	sm._state_machine.state = States.HANDOFF_PENDING

	agentflow_dir = tmp_path / ".agentflow"
	agentflow_dir.mkdir()

	(agentflow_dir / "context_fill.json").write_text(json.dumps({"fill_tokens": 90000, "ts": time.time()}))
	(agentflow_dir / "tasks_in_flight.json").write_text("[]")

	with patch.object(sm, "trigger_handoff") as mock_trigger:
		check_drain_restart(sm)
		mock_trigger.assert_not_called()
	assert sm._state_machine.state == States.HANDOFF_PENDING
