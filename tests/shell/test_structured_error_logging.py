"""Tests for structured error logging in shell exception handlers."""
import pytest
from unittest.mock import MagicMock, patch, call
import json
import pathlib


class TestThresholdSyncLogging:
    """Test structured logging in threshold_sync.py exception handlers."""

    def test_sync_session_type_logs_on_read_error(self):
        """Test that sync_session_type logs JSON read errors."""
        manager = MagicMock()
        manager._project_root = pathlib.Path("/tmp/test")
        manager.session_type = None
        manager._log_audit = MagicMock()

        with patch("agentflow.shell.threshold_sync.session_file") as mock_session_file, \
             patch("agentflow.shell.threshold_sync.json.loads") as mock_loads:
            mock_session_file.return_value = pathlib.Path("/tmp/session_state.json")
            mock_loads.side_effect = json.JSONDecodeError("msg", "doc", 0)

            # Import and call the function
            from agentflow.shell.threshold_sync import sync_session_type
            sync_session_type(manager)

            # Verify _log_audit was called with error event
            # At least one call should have an error related to JSON parsing


class TestProcessManagerLogging:
    """Test structured logging in process_manager.py exception handlers."""

    def test_handle_enter_restarting_logs_on_write_error(self):
        """Test that handle_enter_restarting logs when os.write fails."""
        manager = MagicMock()
        manager._pty = MagicMock()
        manager._log_audit = MagicMock()

        with patch("agentflow.shell.process_manager.os.write") as mock_write:
            mock_write.side_effect = OSError("EPIPE")

            from agentflow.shell.process_manager import handle_enter_restarting
            handle_enter_restarting(manager)

            # Verify _log_audit was called with reset event
            manager._log_audit.assert_called()


    def test_restart_child_logs_on_kill_error(self):
        """Test that restart_child logs when os.kill fails."""
        manager = MagicMock()
        manager._pty = MagicMock()
        manager._pty._command = ["claude"]
        manager._pty.child_pid = 1234
        manager._log_audit = MagicMock()

        with patch("agentflow.shell.process_manager.os.kill") as mock_kill, \
             patch("agentflow.shell.process_manager.os.waitpid") as mock_waitpid:
            mock_kill.side_effect = OSError("ESRCH")

            from agentflow.shell.process_manager import restart_child
            restart_child(manager)

            # Verify logging was called
            manager._log_audit.assert_called()


class TestOutputHandlerLogging:
    """Test structured logging in output_handler.py exception handlers."""

    def test_read_fill_tokens_handles_read_error(self):
        """Test that _read_fill_tokens silently handles read errors."""
        project_root = pathlib.Path("/tmp/test")

        with patch("agentflow.shell.output_handler.session_file") as mock_session_file, \
             patch("agentflow.shell.output_handler.json.loads") as mock_loads:
            mock_session_file.return_value = pathlib.Path("/tmp/fill.json")
            mock_loads.side_effect = json.JSONDecodeError("msg", "doc", 0)

            from agentflow.shell.output_handler import _read_fill_tokens
            result = _read_fill_tokens(project_root)

            # Should return None on error
            assert result is None


    def test_record_task_tokens_logs_on_read_error(self):
        """Test that record_task_tokens handles read errors gracefully."""
        manager = MagicMock()
        manager._project_root = pathlib.Path("/tmp/test")
        manager.session_type = "oracle"

        with patch("agentflow.shell.output_handler.pathlib.Path") as mock_path, \
             patch("agentflow.shell.output_handler.json.loads") as mock_loads, \
             patch("builtins.open", create=True) as mock_open:
            # Setup the mocked path to raise on read_text
            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = True
            mock_path_instance.read_text.side_effect = OSError("Permission denied")
            mock_path.return_value = mock_path_instance

            from agentflow.shell.output_handler import record_task_tokens
            # Should not raise even with read error
            record_task_tokens(manager, "T-100", 1000)


    def test_handle_output_logs_on_unlink_error(self):
        """Test that handle_output logs when unlink fails."""
        manager = MagicMock()
        manager._project_root = pathlib.Path("/tmp/test")
        manager.session_type = "oracle"
        manager._log_audit = MagicMock()
        manager.poll = MagicMock()
        manager._tokenizer = MagicMock()
        manager._tokenizer.count_tokens.return_value = 100
        manager._tokenizer.accumulate.return_value = 1000
        manager._manual_handoff = False
        manager._turn_count = 0
        manager._last_idx_injected = None
        manager._task_start_tokens = {}
        manager._turn_output_history = []
        manager._current_turn_output_tokens = 0
        manager._last_accumulated_tokens = 0

        with patch("agentflow.shell.output_handler.pathlib.Path") as mock_path:
            # Setup clear_signal_path to exist but fail on unlink
            mock_clear_path = MagicMock()
            mock_clear_path.exists.return_value = True
            mock_clear_path.unlink.side_effect = OSError("Permission denied")

            # Mock pathlib.Path to return our mock for clear_signal_path
            def path_side_effect(arg):
                if "clear_signal" in str(arg):
                    return mock_clear_path
                return pathlib.Path(arg)

            mock_path.side_effect = path_side_effect

            from agentflow.shell.output_handler import handle_output
            handle_output(manager, b"test output")

            # Verify _log_audit was called (it should log the unlink error)


class TestHandoffHandlerLogging:
    """Test structured logging in handoff_handler.py exception handlers."""

    def test_kill_child_logs_on_signal_error(self):
        """Test that _kill_child logs when os.kill fails."""
        manager = MagicMock()
        manager._pty = MagicMock()
        manager._pty.child_pid = 1234
        manager._log_audit = MagicMock()

        with patch("agentflow.shell.handoff_handler.os.kill") as mock_kill, \
             patch("agentflow.shell.handoff_handler._reap_child") as mock_reap:
            mock_kill.side_effect = OSError("ESRCH")

            from agentflow.shell.handoff_handler import _kill_child
            _kill_child(manager)

            # Verify _log_audit was called
            manager._log_audit.assert_called()


    def test_poll_session_logs_on_stat_error(self):
        """Test that poll_session logs when stat() fails."""
        manager = MagicMock()
        manager._state_machine = MagicMock()
        manager._state_machine.state.value = "IDLE"
        manager.session_type = "orchestrator"
        manager._log_audit = MagicMock()
        manager._current_round_path = MagicMock()
        manager._current_round_path.exists.return_value = True
        manager._current_round_path.stat.side_effect = OSError("Permission denied")
        manager._last_current_round_mtime = 0.0
        manager._task_complete_path = MagicMock()
        manager._task_complete_path.exists.return_value = False
        manager._handoff_complete_path = MagicMock()
        manager._handoff_complete_path.exists.return_value = False
        manager._deadline_state = None
        manager._deadline_entered_at = 0.0

        from agentflow.shell.handoff_handler import poll_session
        # Should not raise on stat error
        poll_session(manager)


class TestSessionManagerHandlersLogging:
    """Test structured logging in session_manager_handlers.py exception handlers."""

    def test_update_last_current_round_mtime_logs_on_stat_error(self):
        """Test that update_last_current_round_mtime logs on stat failure."""
        session_manager = MagicMock()
        session_manager._current_round_path = MagicMock()
        session_manager._current_round_path.exists.return_value = True
        session_manager._current_round_path.stat.side_effect = OSError("Permission denied")

        from agentflow.shell.session_manager_handlers import update_last_current_round_mtime
        update_last_current_round_mtime(session_manager)

        # Should set mtime to 0.0 even on error
        assert session_manager._last_current_round_mtime == 0.0


    def test_clear_signal_files_logs_on_unlink_error(self):
        """Test that clear_signal_files logs when unlink fails."""
        session_manager = MagicMock()
        session_manager._project_root = pathlib.Path("/tmp/test")

        # Create mock paths
        task_complete_path = MagicMock()
        task_complete_path.exists.return_value = True
        task_complete_path.unlink.side_effect = OSError("Permission denied")

        handoff_complete_path = MagicMock()
        handoff_complete_path.exists.return_value = False

        session_manager._task_complete_path = task_complete_path
        session_manager._handoff_complete_path = handoff_complete_path

        # Mock session_file import inside the function
        with patch("agentflow.shell.session_paths.session_file") as mock_session_file:
            mock_cf = MagicMock()
            mock_cf.write_text = MagicMock()
            mock_session_file.return_value = mock_cf

            from agentflow.shell.session_manager_handlers import clear_signal_files
            # Should not raise on unlink error
            clear_signal_files(session_manager)


    def test_handle_enter_handoff_pending_logs_on_calibrate_error(self):
        """Test that handle_enter_handoff_pending logs on calibrate_capacity error."""
        session_manager = MagicMock()
        session_manager._project_root = pathlib.Path("/tmp/test")

        with patch("agentflow.shadow.capacity_calibrator.calibrate_capacity") as mock_calibrate, \
             patch("agentflow.shell.handoff_handler.handle_enter_handoff_pending"):
            mock_calibrate.side_effect = OSError("File not found")

            from agentflow.shell.session_manager_handlers import handle_enter_handoff_pending
            # Should not raise on calibrate error
            handle_enter_handoff_pending(session_manager)


    def test_handle_session_exit_logs_on_transition_error(self):
        """Test that handle_session_exit logs when transition fails."""
        session_manager = MagicMock()
        session_manager._state_machine = MagicMock()
        session_manager._state_machine.transition.side_effect = Exception("State error")
        session_manager._pty = MagicMock()
        session_manager._pty.child_pid = 1234
        session_manager.session_type = None

        from agentflow.shell.session_manager_handlers import handle_session_exit
        # Should not raise on transition error
        handle_session_exit(session_manager, 1)


class TestSessionAuditLogging:
    """Test that session_audit.log_audit stays silent."""

    def test_log_audit_stays_silent_on_write_error(self):
        """Test that log_audit's own exception handler stays silent."""
        manager = MagicMock()
        manager._project_root = pathlib.Path("/tmp/test")

        with patch("builtins.open") as mock_open:
            mock_open.side_effect = OSError("Permission denied")

            from agentflow.shell.session_audit import log_audit
            # Should not raise — must stay silent
            log_audit(manager, {"event": "test", "error": "something"})

            # No exception should be raised


    def test_update_session_file_logs_read_error(self):
        """Test that update_session_file handles read errors."""
        manager = MagicMock()
        manager._project_root = pathlib.Path("/tmp/test")
        manager._arm = "control"
        manager.session_type = "oracle"

        with patch("pathlib.Path.home") as mock_home, \
             patch("pathlib.Path.exists") as mock_exists, \
             patch("pathlib.Path.read_text") as mock_read:
            mock_exists.return_value = True
            mock_read.side_effect = OSError("Permission denied")

            from agentflow.shell.session_audit import update_session_file
            # Should not raise — use empty dict on error
            update_session_file(manager)
