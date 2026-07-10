"""Tests for drain-restart logic (T-187) and session_lifecycle delegation (T-175)."""
from __future__ import annotations
import json
import pathlib
from unittest.mock import MagicMock, patch, call
import pytest
from agentflow.shell.session_manager import SessionManager
from agentflow.shell.state_machine import States
from tests.shell.conftest import make_manager


class TestDrainRestart:
    """Test check_drain_restart trigger conditions."""

    def test_drain_restart_fires(self, tmp_path):
        """Orchestrator, IDLE, tasks_in_flight absent, current_round exists, fill_tokens >= threshold."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "orchestrator"
        sm._state_machine.state = States.IDLE

        # Set up required files
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "current_round.json").write_text('{"task":"T-001"}')
        (agentflow_dir / "context_fill.json").write_text(json.dumps({"fill_tokens": 90000, "ts": "2026-07-10T00:00:00"}))

        # Mock trigger_handoff to verify it was called
        with patch.object(sm, "trigger_handoff") as mock_trigger:
            from agentflow.shell.session_lifecycle import check_drain_restart
            check_drain_restart(sm)
            mock_trigger.assert_called_once_with(trigger="drain")

    def test_drain_restart_no_fire_wrong_session_type(self, tmp_path):
        """Oracle session does not trigger drain restart."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "oracle"
        sm._state_machine.state = States.IDLE

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "current_round.json").write_text('{"task":"T-001"}')
        (agentflow_dir / "context_fill.json").write_text(json.dumps({"fill_tokens": 90000, "ts": "2026-07-10T00:00:00"}))

        with patch.object(sm, "trigger_handoff") as mock_trigger:
            from agentflow.shell.session_lifecycle import check_drain_restart
            check_drain_restart(sm)
            mock_trigger.assert_not_called()

    def test_drain_restart_no_fire_not_idle(self, tmp_path):
        """TASK_RUNNING state does not trigger drain restart."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "orchestrator"
        sm._state_machine.state = States.TASK_RUNNING

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "current_round.json").write_text('{"task":"T-001"}')
        (agentflow_dir / "context_fill.json").write_text(json.dumps({"fill_tokens": 90000, "ts": "2026-07-10T00:00:00"}))

        with patch.object(sm, "trigger_handoff") as mock_trigger:
            from agentflow.shell.session_lifecycle import check_drain_restart
            check_drain_restart(sm)
            mock_trigger.assert_not_called()

    def test_drain_restart_no_fire_fill_below_threshold(self, tmp_path):
        """fill_tokens below threshold does not trigger."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "orchestrator"
        sm._state_machine.state = States.IDLE

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "current_round.json").write_text('{"task":"T-001"}')
        (agentflow_dir / "context_fill.json").write_text(json.dumps({"fill_tokens": 40000, "ts": "2026-07-10T00:00:00"}))

        with patch.object(sm, "trigger_handoff") as mock_trigger:
            from agentflow.shell.session_lifecycle import check_drain_restart
            check_drain_restart(sm)
            mock_trigger.assert_not_called()

    def test_drain_restart_no_fire_tasks_still_in_flight(self, tmp_path):
        """Tasks in flight does not trigger drain restart."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "orchestrator"
        sm._state_machine.state = States.IDLE

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "current_round.json").write_text('{"task":"T-001"}')
        (agentflow_dir / "context_fill.json").write_text(json.dumps({"fill_tokens": 90000, "ts": "2026-07-10T00:00:00"}))
        (agentflow_dir / "tasks_in_flight.json").write_text(json.dumps(["T-001"]))

        with patch.object(sm, "trigger_handoff") as mock_trigger:
            from agentflow.shell.session_lifecycle import check_drain_restart
            check_drain_restart(sm)
            mock_trigger.assert_not_called()

    def test_drain_restart_no_fire_no_round(self, tmp_path):
        """Missing current_round.json does not trigger (prevents startup trigger)."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "orchestrator"
        sm._state_machine.state = States.IDLE

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "context_fill.json").write_text(json.dumps({"fill_tokens": 90000, "ts": "2026-07-10T00:00:00"}))

        with patch.object(sm, "trigger_handoff") as mock_trigger:
            from agentflow.shell.session_lifecycle import check_drain_restart
            check_drain_restart(sm)
            mock_trigger.assert_not_called()

    def test_drain_restart_no_fire_context_fill_absent(self, tmp_path):
        """Missing context_fill.json treats fill_tokens as 0 (below threshold)."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "orchestrator"
        sm._state_machine.state = States.IDLE

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "current_round.json").write_text('{"task":"T-001"}')

        with patch.object(sm, "trigger_handoff") as mock_trigger:
            from agentflow.shell.session_lifecycle import check_drain_restart
            check_drain_restart(sm)
            mock_trigger.assert_not_called()

    def test_drain_restart_no_fire_handoff_in_progress(self, tmp_path):
        """Handoff in progress prevents drain restart."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "orchestrator"
        sm._state_machine.state = States.HANDOFF_PENDING

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "current_round.json").write_text('{"task":"T-001"}')
        (agentflow_dir / "context_fill.json").write_text(json.dumps({"fill_tokens": 90000, "ts": "2026-07-10T00:00:00"}))

        with patch.object(sm, "trigger_handoff") as mock_trigger:
            from agentflow.shell.session_lifecycle import check_drain_restart
            check_drain_restart(sm)
            mock_trigger.assert_not_called()

    def test_drain_restart_no_fire_handoff_disabled(self, tmp_path):
        """handoff_disabled file prevents drain restart."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "orchestrator"
        sm._state_machine.state = States.IDLE

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "current_round.json").write_text('{"task":"T-001"}')
        (agentflow_dir / "context_fill.json").write_text(json.dumps({"fill_tokens": 90000, "ts": "2026-07-10T00:00:00"}))
        (agentflow_dir / "handoff_disabled").write_text("")

        with patch.object(sm, "trigger_handoff") as mock_trigger:
            from agentflow.shell.session_lifecycle import check_drain_restart
            check_drain_restart(sm)
            mock_trigger.assert_not_called()


class TestSessionLifecycleDelegation:
    """Test that session_manager methods delegate to session_lifecycle."""

    def test_check_drain_restart_method_delegates(self, tmp_path):
        """_check_drain_restart calls check_drain_restart function."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "orchestrator"
        sm._state_machine.state = States.IDLE

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "current_round.json").write_text('{"task":"T-001"}')
        (agentflow_dir / "context_fill.json").write_text(json.dumps({"fill_tokens": 90000, "ts": "2026-07-10T00:00:00"}))

        with patch.object(sm, "trigger_handoff") as mock_trigger:
            sm._check_drain_restart()
            mock_trigger.assert_called_once_with(trigger="drain")

    def test_on_idle_tick_calls_drain_check(self, tmp_path):
        """on_idle_tick calls _check_drain_restart after poll."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path

        with patch.object(sm, "_check_drain_restart") as mock_drain, \
             patch.object(sm, "poll"), \
             patch.object(sm, "_sync_session_type"), \
             patch.object(sm, "_run_stale_index_guard"):
            sm.on_idle_tick()
            mock_drain.assert_called_once()

    def test_sync_session_type_delegates(self, tmp_path):
        """_sync_session_type delegates to session_lifecycle.sync_session_type."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        (agentflow_dir / "session_type").write_text("orchestrator")

        with patch("agentflow.shell.session_lifecycle.sync_session_type") as mock_sync:
            sm._sync_session_type()
            mock_sync.assert_called_once_with(sm)

    def test_apply_session_threshold_delegates(self, tmp_path):
        """_apply_session_threshold delegates to session_lifecycle."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "orchestrator"

        with patch("agentflow.shell.session_lifecycle.apply_session_threshold") as mock_apply:
            sm._apply_session_threshold()
            mock_apply.assert_called_once_with(sm)

    def test_update_session_file_delegates(self, tmp_path):
        """_update_session_file delegates to session_lifecycle."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path

        with patch("agentflow.shell.session_lifecycle.update_session_file") as mock_update:
            sm._update_session_file()
            mock_update.assert_called_once_with(sm)

    def test_log_audit_delegates(self, tmp_path):
        """_log_audit delegates to session_lifecycle."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path

        with patch("agentflow.shell.session_lifecycle.log_audit") as mock_log:
            entry = {"event": "test"}
            sm._log_audit(entry)
            mock_log.assert_called_once_with(sm, entry)
