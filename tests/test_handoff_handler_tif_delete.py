"""Tests for T-256: delete tasks_in_flight.json in _write_merged_and_clear to prevent restart loop."""
from __future__ import annotations
import json
import time
from unittest.mock import MagicMock, patch
import pytest
from agentflow.shell.state_machine import States
from tests.shell.conftest import make_manager


class TestWriteMergedAndClearDeletesTif:
    """T-256: _write_merged_and_clear must delete tasks_in_flight.json after drain."""

    def test_write_merged_and_clear_deletes_tif_after_drain(self, tmp_path):
        """After _write_merged_and_clear succeeds, tasks_in_flight.json must not exist."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()

        # Set up current_round.json with task IDs
        (agentflow_dir / "current_round.json").write_text(
            json.dumps({"round_id": "R-001", "task_ids": ["T-256"]})
        )

        # Create tasks_in_flight.json with empty list (the problematic tombstone)
        tif_path = agentflow_dir / "tasks_in_flight.json"
        tif_path.write_text("[]")
        sm._tasks_in_flight_path = tif_path

        # Create execution_plan.md with a task line
        ep_path = tmp_path / "execution_plan.md"
        ep_path.write_text("## Addendum: T-256\n\n## Addendum: T-257\n")
        sm._config = {}
        sm._log_audit = MagicMock()

        from agentflow.shell.handoff_handler import _write_merged_and_clear
        _write_merged_and_clear(sm)

        # After the function runs, tasks_in_flight.json must not exist
        assert not tif_path.exists(), "tasks_in_flight.json should be deleted after _write_merged_and_clear"

    def test_write_merged_and_clear_tif_absent_is_noop(self, tmp_path):
        """If tasks_in_flight.json was already absent, function completes without error."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()

        # Set up current_round.json
        (agentflow_dir / "current_round.json").write_text(
            json.dumps({"round_id": "R-001", "task_ids": ["T-256"]})
        )

        # Ensure tasks_in_flight.json does NOT exist
        tif_path = agentflow_dir / "tasks_in_flight.json"
        assert not tif_path.exists()
        sm._tasks_in_flight_path = tif_path

        # Create execution_plan.md
        ep_path = tmp_path / "execution_plan.md"
        ep_path.write_text("## Addendum: T-256\n")
        sm._config = {}
        sm._log_audit = MagicMock()

        # Function should not raise even though tif doesn't exist
        from agentflow.shell.handoff_handler import _write_merged_and_clear
        _write_merged_and_clear(sm)

        # File should still not exist (noop, not created)
        assert not tif_path.exists()

    def test_check_drain_skips_when_tif_absent_after_restart(self, tmp_path):
        """After _write_merged_and_clear, check_drain_restart sees no tif file and skips."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "orchestrator"
        sm._state_machine.state = States.IDLE

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()

        # Set up current_round.json
        (agentflow_dir / "current_round.json").write_text('{"round_id":"R-001","task_ids":["T-256"]}')

        # Initially create tasks_in_flight.json and set up paths
        tif_path = agentflow_dir / "tasks_in_flight.json"
        tif_path.write_text("[]")
        sm._tasks_in_flight_path = tif_path

        # Set up execution_plan.md
        ep_path = tmp_path / "execution_plan.md"
        ep_path.write_text("## Addendum: T-256\n")
        sm._config = {"handoff_primary_tokens": 80000}
        sm._log_audit = MagicMock()

        # Set high context fill so drain would normally trigger
        (agentflow_dir / "context_fill.json").write_text(
            json.dumps({"fill_tokens": 90000, "ts": time.time()})
        )

        # Call _write_merged_and_clear to delete tif
        from agentflow.shell.handoff_handler import _write_merged_and_clear
        _write_merged_and_clear(sm)
        assert not tif_path.exists(), "tif should be deleted by _write_merged_and_clear"

        # Now call check_drain_restart with high fill_tokens
        # It should skip because tif doesn't exist, not trigger restart
        with patch.object(sm._state_machine, "transition") as mock_transition:
            from agentflow.shell.handoff_handler import check_drain_restart
            check_drain_restart(sm)
            # Should not transition to restart because tif is absent
            mock_transition.assert_not_called()

        assert sm._state_machine.state == States.IDLE

    def test_normal_drain_restart_still_works(self, tmp_path):
        """Normal drain restart works: tif=[], fill=90K → restart triggered; tif deleted."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "orchestrator"
        sm._state_machine.state = States.IDLE

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()

        # Set up files
        (agentflow_dir / "current_round.json").write_text('{"round_id":"R-001","task_ids":["T-256"]}')
        tif_path = agentflow_dir / "tasks_in_flight.json"
        tif_path.write_text("[]")
        sm._tasks_in_flight_path = tif_path

        (agentflow_dir / "context_fill.json").write_text(
            json.dumps({"fill_tokens": 90000, "ts": time.time()})
        )

        ep_path = tmp_path / "execution_plan.md"
        ep_path.write_text("## Addendum: T-256\n")

        sm._config = {"handoff_primary_tokens": 80000}
        sm._log_audit = MagicMock()
        sm._handoff_in_progress = False

        def mock_auto_handoff_disabled():
            return False
        sm._auto_handoff_disabled = mock_auto_handoff_disabled

        # Trigger check_drain_restart
        with patch.object(sm._state_machine, "on_enter_restarting"):
            from agentflow.shell.handoff_handler import check_drain_restart
            check_drain_restart(sm)

        # Should have transitioned to RESTARTING
        assert sm._state_machine.state == States.RESTARTING

        # tasks_in_flight.json should be deleted
        assert not tif_path.exists(), "tif should be deleted when restart is triggered"

    def test_drain_does_not_refire_when_no_tasks_started(self, tmp_path):
        """On session restart with high fill but no tif file, check_drain_restart skips."""
        sm, pty, tok = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "orchestrator"
        sm._state_machine.state = States.IDLE

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()

        (agentflow_dir / "current_round.json").write_text('{"round_id":"R-001"}')

        # tasks_in_flight.json does NOT exist (simulating after restart cleanup)
        tif_path = agentflow_dir / "tasks_in_flight.json"
        sm._tasks_in_flight_path = tif_path
        assert not tif_path.exists()

        # Even with high fill_tokens
        (agentflow_dir / "context_fill.json").write_text(
            json.dumps({"fill_tokens": 90000, "ts": time.time()})
        )

        sm._config = {"handoff_primary_tokens": 80000}
        sm._log_audit = MagicMock()
        sm._handoff_in_progress = False

        def mock_auto_handoff_disabled():
            return False
        sm._auto_handoff_disabled = mock_auto_handoff_disabled

        # Call check_drain_restart
        from agentflow.shell.handoff_handler import check_drain_restart
        check_drain_restart(sm)

        # Should NOT transition to RESTARTING
        # (caught by "no_tasks_in_flight_file" skip guard)
        assert sm._state_machine.state == States.IDLE
