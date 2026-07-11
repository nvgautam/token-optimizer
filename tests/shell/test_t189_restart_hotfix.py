"""Tests for T-189 PTY restart hotfix — 4 targeted fixes for restart storms and cross-session poisoning.

Test coverage:
1. cooldown_guard: check_drain_restart respects 30s cooldown after _last_restart_ts
2. context_fill_reset: _clear_signal_files zeros context_fill.json on restart
3. delayed_inject: on_enter_idle injects command via 1.5s delayed daemon thread
4. sync_session_type_rerereads: sync_session_type re-reads state files every tick (not just once)
"""
from __future__ import annotations
import json
import pathlib
import threading
import time
from unittest.mock import Mock, patch, MagicMock
import pytest
from agentflow.shell.session_manager import SessionManager
from agentflow.shell.state_machine import States
from tests.shell.conftest import make_manager, FakePTY, FakeTokenizer


class TestCooldownGuard:
    """Fix #2: check_drain_restart has 30s cooldown guard after _last_restart_ts."""

    def test_cooldown_active_blocks_restart(self):
        """When _last_restart_ts is recent, check_drain_restart should return early."""
        sm, pty, tok = make_manager()
        sm.session_type = "orchestrator"
        sm._state_machine.state = States.IDLE

        # Setup context_fill >= threshold
        cf_path = sm._project_root / ".agentflow" / "context_fill.json"
        cf_path.parent.mkdir(parents=True, exist_ok=True)
        cf_path.write_text('{"fill_tokens": 100000}', encoding="utf-8")

        # Setup current_round
        cr_path = sm._current_round_path
        cr_path.parent.mkdir(parents=True, exist_ok=True)
        cr_path.write_text('{}', encoding="utf-8")

        # Setup tasks_in_flight empty (or absent)
        tif_path = sm._project_root / ".agentflow" / "tasks_in_flight.json"
        if tif_path.exists():
            tif_path.unlink()

        # Simulate recent restart (within 30s)
        sm._last_restart_ts = time.monotonic()

        # Call check_drain_restart
        from agentflow.shell.handoff_handler import check_drain_restart
        with patch.object(sm, 'trigger_handoff') as mock_trigger:
            check_drain_restart(sm)
            # Should NOT trigger because cooldown is active
            mock_trigger.assert_not_called()

    def test_cooldown_expired_allows_restart(self):
        """When cooldown has expired (> 30s since restart), restart should be allowed."""
        sm, pty, tok = make_manager()
        sm.session_type = "orchestrator"
        sm._state_machine.state = States.IDLE

        # Setup context_fill >= threshold
        cf_path = sm._project_root / ".agentflow" / "context_fill.json"
        cf_path.parent.mkdir(parents=True, exist_ok=True)
        cf_path.write_text('{"fill_tokens": 100000}', encoding="utf-8")

        # Setup current_round
        cr_path = sm._current_round_path
        cr_path.parent.mkdir(parents=True, exist_ok=True)
        cr_path.write_text('{}', encoding="utf-8")

        # Setup tasks_in_flight empty
        tif_path = sm._project_root / ".agentflow" / "tasks_in_flight.json"
        if tif_path.exists():
            tif_path.unlink()

        # Simulate old restart (> 31s ago)
        sm._last_restart_ts = time.monotonic() - 31.0

        # Call check_drain_restart
        from agentflow.shell.handoff_handler import check_drain_restart
        with patch.object(sm, 'trigger_handoff') as mock_trigger:
            check_drain_restart(sm)
            # Should trigger because cooldown has expired
            mock_trigger.assert_called_once()


class TestContextFillReset:
    """Fix #1: _clear_signal_files zeros context_fill.json on restart."""

    def test_context_fill_reset_on_clear(self):
        """Calling _clear_signal_files should reset context_fill.json fill_tokens to 0."""
        sm, pty, tok = make_manager()

        # Pre-populate context_fill.json with non-zero tokens
        cf_path = sm._project_root / ".agentflow" / "context_fill.json"
        cf_path.parent.mkdir(parents=True, exist_ok=True)
        cf_path.write_text('{"fill_tokens": 90000}', encoding="utf-8")

        # Call _clear_signal_files
        sm._clear_signal_files()

        # Verify context_fill.json now has fill_tokens = 0
        content = json.loads(cf_path.read_text("utf-8"))
        assert content["fill_tokens"] == 0, f"Expected fill_tokens=0, got {content}"

    def test_context_fill_reset_creates_if_missing(self):
        """_clear_signal_files should create context_fill.json if it doesn't exist."""
        sm, pty, tok = make_manager()

        # Ensure .agentflow directory exists but context_fill.json doesn't
        agentflow_dir = sm._project_root / ".agentflow"
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        cf_path = agentflow_dir / "context_fill.json"
        if cf_path.exists():
            cf_path.unlink()

        # Call _clear_signal_files
        sm._clear_signal_files()

        # Verify context_fill.json was created with fill_tokens = 0
        assert cf_path.exists(), "context_fill.json should be created"
        content = json.loads(cf_path.read_text("utf-8"))
        assert content["fill_tokens"] == 0


class TestDelayedInject:
    """T-195: on_enter_idle no longer injects via thread; skill is now a spawn arg."""

    def test_on_enter_idle_no_thread_injection(self):
        """T-195: on_enter_idle clears _just_restarted without spawning a thread or writing to PTY."""
        sm, pty, tok = make_manager()
        sm.session_type = "orchestrator"
        sm._just_restarted = True
        sm.on_enter_idle()
        assert sm._just_restarted is False
        assert len(pty.inputs) == 0, "No PTY injection expected — skill is now a spawn arg"

    def test_on_enter_idle_oracle_no_thread_injection(self):
        """T-195: on_enter_idle does not inject for oracle sessions either."""
        sm, pty, tok = make_manager()
        sm.session_type = "oracle"
        sm._just_restarted = True
        sm.on_enter_idle()
        assert sm._just_restarted is False
        assert len(pty.inputs) == 0

    def test_spawn_new_child_skill_arg_orchestrator(self):
        """T-195: spawn_new_child passes /orchestrate as positional arg on restart."""
        import pty as pty_module
        from agentflow.shell.process_manager import spawn_new_child
        sm, pty, tok = make_manager()
        sm._just_restarted = True
        sm.session_type = "orchestrator"
        exec_called = []
        with patch.object(pty_module, "fork", return_value=(0, 123)), \
             patch("os.execvp", side_effect=lambda cmd, args: exec_called.append(args) or (_ for _ in ()).throw(SystemExit(127))), \
             patch("os._exit"):
            try:
                spawn_new_child(sm)
            except SystemExit:
                pass
        assert exec_called[0] == ["claude", "/orchestrate"]

    def test_delayed_inject_skipped_if_not_just_restarted(self):
        """on_enter_idle should not inject if _just_restarted is False."""
        sm, pty, tok = make_manager()
        sm.session_type = "orchestrator"
        sm._just_restarted = False
        sm.on_enter_idle()
        assert len(pty.inputs) == 0


class TestSyncSessionTypeRereads:
    """Fix #3: sync_session_type re-reads state files every tick (not just once)."""

    def test_sync_session_type_updates_when_already_set(self):
        """sync_session_type should re-read state files even if session_type is already set."""
        sm, pty, tok = make_manager()

        # Pre-set session_type to oracle
        sm.session_type = "oracle"

        # Write a session_state.json with a different session_type
        state_path = sm._project_root / ".agentflow" / "session_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text('{"session_type": "orchestrator"}', encoding="utf-8")

        # Call sync_session_type
        from agentflow.shell.threshold_sync import sync_session_type
        sync_session_type(sm)

        # session_type should be updated to orchestrator (the re-read value)
        assert sm.session_type == "orchestrator", f"Expected orchestrator, got {sm.session_type}"

    def test_sync_session_type_checks_all_files(self):
        """sync_session_type should check session_state_{SID}.json first if AGENTFLOW_SESSION_ID is set."""
        sm, pty, tok = make_manager()
        sm.session_type = None

        # Set AGENTFLOW_SESSION_ID env var
        sid = "test-session-123"
        session_state_sid = sm._project_root / ".agentflow" / f"session_state_{sid}.json"
        session_state_sid.parent.mkdir(parents=True, exist_ok=True)
        session_state_sid.write_text('{"session_type": "orchestrator"}', encoding="utf-8")

        from agentflow.shell.threshold_sync import sync_session_type
        with patch.dict("os.environ", {"AGENTFLOW_SESSION_ID": sid}):
            sync_session_type(sm)

        # Should have read from session_state_{sid}.json
        assert sm.session_type == "orchestrator"

    def test_sync_session_type_fallback_to_session_state(self):
        """If session_state_{SID}.json doesn't exist, sync_session_type should check session_state.json."""
        sm, pty, tok = make_manager()
        sm.session_type = None

        # Write only session_state.json (not session_state_{SID}.json)
        state_path = sm._project_root / ".agentflow" / "session_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text('{"session_type": "oracle"}', encoding="utf-8")

        from agentflow.shell.threshold_sync import sync_session_type
        sync_session_type(sm)

        assert sm.session_type == "oracle"

    def test_sync_session_type_applies_threshold(self):
        """sync_session_type should call apply_session_threshold after updating session_type."""
        sm, pty, tok = make_manager()
        sm.session_type = None

        state_path = sm._project_root / ".agentflow" / "session_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text('{"session_type": "orchestrator"}', encoding="utf-8")

        from agentflow.shell.threshold_sync import sync_session_type
        with patch("agentflow.shell.threshold_sync.apply_session_threshold") as mock_apply:
            sync_session_type(sm)

            # apply_session_threshold should be called
            mock_apply.assert_called()
            assert sm.session_type == "orchestrator"
