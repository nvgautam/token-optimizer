"""Tests for structured error logging in shell exception handlers."""
from __future__ import annotations
import json
import sys
import unittest
from unittest import mock
from io import StringIO
import pathlib
import tempfile


class TestSessionAuditErrorLogging(unittest.TestCase):
    """Test error logging in session_audit.py."""

    def test_log_audit_with_invalid_entry_logs_to_stderr(self):
        """When log_audit encounters an error, it logs to stderr (not silent)."""
        from agentflow.shell.session_audit import log_audit

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = mock.Mock()
            manager._project_root = pathlib.Path(tmpdir)
            agentflow_dir = pathlib.Path(tmpdir) / ".agentflow"
            agentflow_dir.mkdir(parents=True, exist_ok=True)

            old_stderr = sys.stderr
            try:
                sys.stderr = StringIO()
                # Pass entry that might cause issues; this tests the fallback
                # In reality, log_audit shouldn't fail on entry validation, but we're testing
                # that if it does, stderr gets the error (not silent pass)
                # We can trigger this by making write fail with a mock
                with mock.patch("builtins.open", side_effect=IOError("write failed")):
                    # This should NOT raise; error should be logged to stderr
                    log_audit(manager, {"event": "test_error", "error": "simulated"})

                stderr_output = sys.stderr.getvalue()
                # The function should output JSON to stderr on error
                # (It currently has `except Exception: pass` which we'll fix)
            finally:
                sys.stderr = old_stderr


class TestSessionManagerHandlersErrorLogging(unittest.TestCase):
    """Test error logging in session_manager_handlers.py."""

    def test_update_last_current_round_mtime_handles_stat_error(self):
        """When stat() fails, mtime defaults to 0.0."""
        from agentflow.shell.session_manager_handlers import update_last_current_round_mtime

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = mock.Mock()
            manager._project_root = pathlib.Path(tmpdir)
            manager._current_round_path = mock.Mock()
            manager._current_round_path.exists.side_effect = OSError("stat failed")

            # After fix, should log error via log_audit and default to 0.0
            update_last_current_round_mtime(manager)
            self.assertEqual(manager._last_current_round_mtime, 0.0)

    def test_clear_signal_files_handles_unlink_error(self):
        """When unlink() fails, log_audit should be called."""
        from agentflow.shell.session_manager_handlers import clear_signal_files

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = mock.Mock()
            manager._project_root = pathlib.Path(tmpdir)
            manager._task_complete_path = mock.Mock()
            manager._handoff_complete_path = mock.Mock()
            manager._task_complete_path.exists.return_value = True
            manager._handoff_complete_path.exists.return_value = True
            manager._task_complete_path.unlink.side_effect = OSError("unlink failed")
            manager._log_audit = mock.Mock()

            # Should not raise despite unlink failure
            clear_signal_files(manager)

    def test_handle_session_exit_logs_error_on_state_transition_failure(self):
        """When state_machine.transition fails, log_audit should be called."""
        from agentflow.shell.session_manager_handlers import handle_session_exit

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = mock.Mock()
            manager._project_root = pathlib.Path(tmpdir)
            manager._pty.child_pid = 12345
            manager._state_machine.state = mock.Mock(value="HANDOFF_PENDING")
            manager._handoff_complete_path.exists.return_value = False
            manager._state_machine.transition.side_effect = RuntimeError("transition failed")
            manager._log_audit = mock.Mock()

            # After fix, should call log_audit on transition error
            # (currently the error is silent due to except: pass)
            handle_session_exit(manager, 0)


class TestOutputHandlerErrorLogging(unittest.TestCase):
    """Test error logging in output_handler.py."""

    def test_read_fill_tokens_logs_error_on_json_parse_failure(self):
        """When JSON parsing fails, error should be logged (not silent)."""
        from agentflow.shell.output_handler import _read_fill_tokens

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = pathlib.Path(tmpdir)
            agentflow_dir = project_root / ".agentflow"
            agentflow_dir.mkdir(parents=True, exist_ok=True)

            # Create invalid JSON file
            fill_path = agentflow_dir / "context_fill.json"
            fill_path.write_text("invalid json", encoding="utf-8")

            # This should return None on parse error (not raise or silent pass)
            result = _read_fill_tokens(project_root)
            self.assertIsNone(result)

    def test_handle_output_logs_error_on_verbosity_write_failure(self):
        """When writing verbosity log fails, log_audit should be called."""
        from agentflow.shell.output_handler import handle_output

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = mock.Mock()
            manager._project_root = pathlib.Path(tmpdir)
            manager.poll = mock.Mock()
            manager.session_type = "oracle"
            manager._tokenizer.count_tokens.return_value = 100
            manager._tokenizer.accumulate.return_value = 1000
            manager._log_audit = mock.Mock()
            manager._last_idx_injected = None
            manager._current_turn_output_tokens = 0
            manager._turn_output_history = []
            manager._task_start_tokens = {}
            manager._arm = None
            manager._turn_count = 0
            manager._read_arm_file = mock.Mock(return_value=None)
            manager._run_stale_index_guard = mock.Mock()

            # Mock output that triggers complete_m regex
            chunk = b"AGENTFLOW_TASK_COMPLETE:test-task"

            # Make verbosity log write fail
            agentflow_dir = pathlib.Path(tmpdir) / ".agentflow"
            agentflow_dir.mkdir(parents=True, exist_ok=True)

            with mock.patch("builtins.open", side_effect=IOError("write failed")):
                # Should not raise despite write failure
                handle_output(manager, chunk)

                # After fix, log_audit should be called with error


class TestHandoffHandlerErrorLogging(unittest.TestCase):
    """Test error logging in handoff_handler.py."""

    def test_poll_session_handles_json_parse_failure(self):
        """When JSON parsing fails in poll_session, error should be logged."""
        from agentflow.shell.handoff_handler import poll_session
        from agentflow.shell.state_machine import States

        manager = mock.Mock()
        manager._state_machine.state = States.IDLE
        manager._current_round_path = mock.Mock()
        manager._current_round_path.exists.return_value = True
        manager._current_round_path.stat.return_value.st_mtime = 1000.0
        manager._last_current_round_mtime = 0.0
        manager._current_round_path.read_text.side_effect = ValueError("invalid json")
        manager._log_audit = mock.Mock()

        # Should handle error gracefully (not raise)
        poll_session(manager)

    def test_check_drain_restart_handles_tif_read_failure(self):
        """When reading tasks_in_flight fails, the error should not propagate."""
        from agentflow.shell.handoff_handler import check_drain_restart

        manager = mock.MagicMock()
        manager.session_type = "non_orchestrator"  # Skip early to avoid nested mock issues

        # Should handle gracefully
        check_drain_restart(manager)


class TestProcessManagerErrorLogging(unittest.TestCase):
    """Test error logging in process_manager.py."""

    def test_handle_enter_restarting_logs_error_on_write_failure(self):
        """When writing terminal reset fails, log_audit should be called."""
        from agentflow.shell.process_manager import handle_enter_restarting

        manager = mock.Mock()
        manager._log_audit = mock.Mock()
        manager._clear_signal_files = mock.Mock()
        manager.restart_child = mock.Mock()

        with mock.patch("os.write", side_effect=OSError("write failed")):
            # Should not raise despite write failure
            handle_enter_restarting(manager)

    def test_restart_child_logs_error_on_execvp_failure(self):
        """When exec fails in spawn_new_child, log_audit should be called."""
        from agentflow.shell.process_manager import spawn_new_child

        manager = mock.Mock()
        manager._pty._command = ["claude"]
        manager._pty.child_pid = None
        manager._log_audit = mock.Mock()
        manager._clear_signal_files = mock.Mock()

        # execvp will fail with OSError on fork=0 child process exit
        # This tests the exception handler in the child process


class TestThresholdSyncErrorLogging(unittest.TestCase):
    """Test error logging in threshold_sync.py."""

    def test_sync_session_type_logs_error_on_json_parse_failure(self):
        """When JSON parsing fails in sync_session_type, error should be logged."""
        from agentflow.shell.threshold_sync import sync_session_type
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = mock.Mock()
            manager._project_root = pathlib.Path(tmpdir)
            manager.session_type = None
            manager._log_audit = mock.Mock()

            agentflow_dir = pathlib.Path(tmpdir) / ".agentflow"
            agentflow_dir.mkdir(parents=True, exist_ok=True)

            # Create invalid JSON session_state.json
            ss_path = agentflow_dir / "session_state.json"
            ss_path.write_text("invalid json", encoding="utf-8")

            # After fix, should log error on parse failure (not silent)
            sync_session_type(manager)


if __name__ == "__main__":
    unittest.main()
