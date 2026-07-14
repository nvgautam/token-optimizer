"""Tests for T-209: drain restart direct RESTARTING path (no trigger_handoff)."""
from __future__ import annotations
import json
from unittest.mock import patch
import pytest
from agentflow.shell.state_machine import States
from tests.shell.conftest import make_manager


class TestCheckDrainRestartDirectPath:
    """T-209: check_drain_restart transitions directly to RESTARTING, not via trigger_handoff."""

    def test_check_drain_restart_transitions_to_restarting_when_conditions_met(self, tmp_path):
        """tasks_in_flight=[], context_fill=85000, session_type=orchestrator → RESTARTING directly."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "orchestrator"
        sm._state_machine.state = States.IDLE

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "current_round.json").write_text('{"task":"T-001"}')
        (agentflow_dir / "context_fill.json").write_text(
            json.dumps({"fill_tokens": 85000, "ts": "2026-07-10T00:00:00"})
        )
        (agentflow_dir / "tasks_in_flight.json").write_text("[]")

        # on_enter_restarting would call restart_child; patch it to avoid subprocess side effects
        with patch.object(sm, "trigger_handoff") as mock_trigger, \
             patch.object(sm._state_machine, "on_enter_restarting"):
            from agentflow.shell.handoff_handler import check_drain_restart
            check_drain_restart(sm)
            mock_trigger.assert_not_called()

        assert sm._state_machine.state == States.RESTARTING

    def test_check_drain_restart_noop_when_tasks_still_in_flight(self, tmp_path):
        """tasks_in_flight=[T-209], context_fill=85000 → no state transition."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "orchestrator"
        sm._state_machine.state = States.IDLE

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "current_round.json").write_text('{"task":"T-001"}')
        (agentflow_dir / "context_fill.json").write_text(
            json.dumps({"fill_tokens": 85000, "ts": "2026-07-10T00:00:00"})
        )
        (agentflow_dir / "tasks_in_flight.json").write_text(json.dumps(["T-209"]))

        with patch.object(sm, "trigger_handoff") as mock_trigger:
            from agentflow.shell.handoff_handler import check_drain_restart
            check_drain_restart(sm)
            mock_trigger.assert_not_called()

        assert sm._state_machine.state == States.IDLE

    def test_check_drain_restart_noop_when_fill_below_threshold(self, tmp_path):
        """tasks_in_flight=[], context_fill=50000 → no state transition."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "orchestrator"
        sm._state_machine.state = States.IDLE

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "current_round.json").write_text('{"task":"T-001"}')
        (agentflow_dir / "context_fill.json").write_text(
            json.dumps({"fill_tokens": 50000, "ts": "2026-07-10T00:00:00"})
        )
        (agentflow_dir / "tasks_in_flight.json").write_text("[]")

        with patch.object(sm, "trigger_handoff") as mock_trigger:
            from agentflow.shell.handoff_handler import check_drain_restart
            check_drain_restart(sm)
            mock_trigger.assert_not_called()

        assert sm._state_machine.state == States.IDLE

    def test_check_drain_restart_noop_for_oracle_session(self, tmp_path):
        """session_type=oracle → no direct RESTARTING transition (oracle uses HANDOFF_PENDING)."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "oracle"
        sm._state_machine.state = States.IDLE

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "current_round.json").write_text('{"task":"T-001"}')
        (agentflow_dir / "context_fill.json").write_text(
            json.dumps({"fill_tokens": 85000, "ts": "2026-07-10T00:00:00"})
        )
        (agentflow_dir / "tasks_in_flight.json").write_text("[]")

        from agentflow.shell.handoff_handler import check_drain_restart
        check_drain_restart(sm)

        # Oracle session must not transition to RESTARTING directly
        assert sm._state_machine.state == States.IDLE

    def test_process_manager_clear_signal_files_before_execvp(self, tmp_path):
        """clear_signal_files() is called before restart_child in handle_enter_restarting."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path

        call_order: list[str] = []

        def mock_clear():
            call_order.append("clear_signal_files")

        def mock_restart():
            call_order.append("restart_child")

        with patch.object(sm, "_clear_signal_files", side_effect=mock_clear), \
             patch.object(sm, "restart_child", side_effect=mock_restart):
            from agentflow.shell.process_manager import handle_enter_restarting
            handle_enter_restarting(sm)

        assert "clear_signal_files" in call_order
        assert "restart_child" in call_order
        assert call_order.index("clear_signal_files") < call_order.index("restart_child")
