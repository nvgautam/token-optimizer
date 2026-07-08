"""Tests for output_handler.py — turn boundary detection and verbosity logging."""
import unittest
from unittest.mock import Mock, patch
import json
import pathlib
import tempfile
import os
import datetime

from agentflow.shell.output_handler import handle_output, record_task_tokens, ansi_strip
from agentflow.shell.state_machine import States


class TestOutputHandler(unittest.TestCase):
    """Test suite for output handling and turn boundary detection."""

    def _create_mock_manager(self):
        """Factory for a properly configured mock manager."""
        manager = Mock()
        manager._project_root = pathlib.Path("/tmp/test_project")
        manager.session_type = "oracle"
        manager._turn_count = 0
        manager._arm = "A"
        manager._last_had_content = False
        manager._current_turn_output_tokens = 0
        manager._turn_output_history = []
        manager._task_start_tokens = {}
        manager._last_idx_injected = None
        manager._manual_handoff = False
        manager._last_restart_ts = 0
        manager._last_accumulated_tokens = 0
        manager._state_machine = Mock()
        manager._state_machine.state = States.HANDOFF_PENDING
        manager._tokenizer = Mock()
        manager._tokenizer.count_tokens = Mock(return_value=10)
        manager._tokenizer.accumulate = Mock(return_value=100)
        manager.poll = Mock()
        manager._update_session_file = Mock()
        manager._read_arm_file = Mock(return_value="B")
        manager._log_audit = Mock()
        manager._auto_handoff_disabled = Mock(return_value=False)
        manager._run_stale_index_guard = Mock()
        manager._config = {"handoff_primary_tokens": 80000}
        manager._handoff_complete_path = pathlib.Path("/tmp/handoff_complete.json")
        return manager

    def test_handle_output_turn_boundary_on_task_complete(self):
        """Turn boundary is recorded when AGENTFLOW_TASK_COMPLETE is detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = self._create_mock_manager()
            project_root = pathlib.Path(tmpdir)
            manager._project_root = project_root
            agentflow_dir = project_root / ".agentflow"
            agentflow_dir.mkdir(parents=True, exist_ok=True)

            manager.session_type = "oracle"
            manager._turn_count = 0
            manager._task_start_tokens = {"T-001": 50}

            chunk = b"Some output\nAGENTFLOW_TASK_COMPLETE:T-001\n"
            handle_output(manager, chunk)

            # Verify turn_count incremented
            self.assertEqual(manager._turn_count, 1)

            # Verify verbosity_log.jsonl was written
            verbosity_log = agentflow_dir / "verbosity_log.jsonl"
            self.assertTrue(verbosity_log.exists())

            with open(verbosity_log, "r") as f:
                lines = f.readlines()
                self.assertGreater(len(lines), 0)
                entry = json.loads(lines[-1])
                self.assertEqual(entry["turn"], 1)
                self.assertIn("output_tokens", entry)
                self.assertIn("ts", entry)
                self.assertEqual(entry["session_type"], "oracle")

    def test_handle_output_no_boundary_on_double_newline(self):
        """Double newline does NOT trigger turn boundary (old heuristic removed)."""
        manager = self._create_mock_manager()
        manager._turn_count = 0
        manager._last_had_content = True

        chunk = b"Some output\n\nMore output\n"
        handle_output(manager, chunk)

        # Turn count must NOT increment from double newline alone
        self.assertEqual(manager._turn_count, 0)

    def test_handle_output_arm_read_on_first_turn(self):
        """_read_arm_file() is called when turn_count becomes 1 on task complete."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = self._create_mock_manager()
            project_root = pathlib.Path(tmpdir)
            manager._project_root = project_root
            agentflow_dir = project_root / ".agentflow"
            agentflow_dir.mkdir(parents=True, exist_ok=True)

            manager.session_type = "oracle"
            manager._turn_count = 0
            manager._read_arm_file = Mock(return_value="B")
            manager._task_start_tokens = {"T-001": 50}

            chunk = b"Output\nAGENTFLOW_TASK_COMPLETE:T-001\n"
            handle_output(manager, chunk)

            # Verify _read_arm_file was called on first turn
            manager._read_arm_file.assert_called()
            self.assertEqual(manager._arm, "B")

    def test_handle_output_turn_state_management(self):
        """Turn state is properly maintained and reset."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = self._create_mock_manager()
            project_root = pathlib.Path(tmpdir)
            manager._project_root = project_root
            agentflow_dir = project_root / ".agentflow"
            agentflow_dir.mkdir(parents=True, exist_ok=True)

            # Test history trimming
            manager._turn_output_history = [100] * 10
            manager._current_turn_output_tokens = 50
            manager._task_start_tokens = {"T-001": 50}
            manager._tokenizer.count_tokens = Mock(return_value=10)

            chunk = b"Output\nAGENTFLOW_TASK_COMPLETE:T-001\n"
            handle_output(manager, chunk)

            # Verify history trimmed and state reset
            self.assertEqual(len(manager._turn_output_history), 10)
            self.assertEqual(manager._turn_output_history[-1], 60)
            self.assertEqual(manager._current_turn_output_tokens, 0)

            # Test subsequent call resets idx_injected
            manager._last_idx_injected = "some_path.py"
            manager._task_start_tokens = {"T-002": 100}
            handle_output(manager, b"Output\nAGENTFLOW_TASK_COMPLETE:T-002\n")
            self.assertIsNone(manager._last_idx_injected)

    def test_record_task_tokens_writes_jsonl(self):
        """record_task_tokens writes a proper entry to task_token_log.jsonl."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = self._create_mock_manager()
            project_root = pathlib.Path(tmpdir) / "project"
            project_root.mkdir(parents=True, exist_ok=True)

            agentflow_dir = project_root / ".agentflow"
            agentflow_dir.mkdir(parents=True, exist_ok=True)

            manager._project_root = project_root
            manager.session_type = "orchestrator"

            with patch("pathlib.Path.home", return_value=pathlib.Path(tmpdir)):
                record_task_tokens(manager, "T-001", 100)

            log_path = pathlib.Path(tmpdir) / ".agentflow" / "task_token_log.jsonl"
            self.assertTrue(log_path.exists())

            with open(log_path, "r") as f:
                line = f.readline()
                entry = json.loads(line)
                self.assertEqual(entry["task_id"], "T-001")
                self.assertEqual(entry["token_delta"], 100)
                self.assertEqual(entry["session_type"], "orchestrator")
                self.assertIn("timestamp", entry)


    def test_ansi_strip(self):
        """ANSI escape codes are stripped from text."""
        text = "Hello \x1b[31mWorld\x1b[0m"
        result = ansi_strip(text)
        self.assertEqual(result, "Hello World")

    def test_ansi_strip_comprehensive(self):
        """ANSI codes are stripped correctly in various formats."""
        # Multiple codes
        text1 = "\x1b[1m\x1b[32mGreen Bold\x1b[0m"
        self.assertEqual(ansi_strip(text1), "Green Bold")
        # Plain text unchanged
        text2 = "Plain text"
        self.assertEqual(ansi_strip(text2), "Plain text")

    def test_handle_output_multiple_task_completes_in_sequence(self):
        """Multiple task complete signals increment turn count correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = self._create_mock_manager()
            project_root = pathlib.Path(tmpdir)
            manager._project_root = project_root
            agentflow_dir = project_root / ".agentflow"
            agentflow_dir.mkdir(parents=True, exist_ok=True)

            manager.session_type = "oracle"
            manager._turn_count = 0

            # First task complete
            manager._task_start_tokens = {"T-001": 50}
            chunk1 = b"Output 1\nAGENTFLOW_TASK_COMPLETE:T-001\n"
            handle_output(manager, chunk1)
            self.assertEqual(manager._turn_count, 1)

            # Second task complete
            manager._task_start_tokens = {"T-002": 100}
            manager._tokenizer.accumulate = Mock(return_value=200)
            chunk2 = b"Output 2\nAGENTFLOW_TASK_COMPLETE:T-002\n"
            handle_output(manager, chunk2)
            self.assertEqual(manager._turn_count, 2)

            # Verify both entries in verbosity log
            verbosity_log = agentflow_dir / "verbosity_log.jsonl"
            with open(verbosity_log, "r") as f:
                lines = f.readlines()
                self.assertEqual(len(lines), 2)

    def test_handle_output_clear_command_resets_state(self):
        """Clearing the session resets turn count and session type."""
        manager = self._create_mock_manager()
        manager.session_type = "oracle"
        manager._turn_count = 5

        chunk = b"/clear\n"
        handle_output(manager, chunk)

        # Verify state reset
        self.assertIsNone(manager.session_type)
        self.assertEqual(manager._turn_count, 0)
        manager._update_session_file.assert_called()

    def test_handle_output_session_type_transition(self):
        """Session type transitions correctly on /oracle or /orchestrate."""
        # Oracle transition
        manager1 = self._create_mock_manager()
        manager1.session_type = None
        manager1._read_arm_file = Mock(return_value="A")
        handle_output(manager1, b"/oracle\n")
        self.assertEqual(manager1.session_type, "oracle")

        # Orchestrator transition
        manager2 = self._create_mock_manager()
        manager2.session_type = None
        manager2._read_arm_file = Mock(return_value="A")
        handle_output(manager2, b"/orchestrate\n")
        self.assertEqual(manager2.session_type, "orchestrator")


    def test_handle_output_task_signal_tracking(self):
        """Task start and complete signals are tracked and handled."""
        # Test task start tracking
        manager1 = self._create_mock_manager()
        manager1._task_start_tokens = {}
        manager1._tokenizer.accumulate = Mock(return_value=100)
        handle_output(manager1, b"Starting\nAGENTFLOW_TASK_START:T-001\n")
        self.assertIn("T-001", manager1._task_start_tokens)

        # Test complete without start (still increments turn)
        manager2 = self._create_mock_manager()
        manager2._task_start_tokens = {}
        manager2._turn_count = 0
        handle_output(manager2, b"Completing\nAGENTFLOW_TASK_COMPLETE:T-001\n")
        self.assertEqual(manager2._turn_count, 1)

    def test_handle_output_token_management(self):
        """Token accumulation and exception handling work correctly."""
        # Test token accumulation
        manager = self._create_mock_manager()
        manager._tokenizer.count_tokens = Mock(return_value=25)
        manager._tokenizer.accumulate = Mock(return_value=150)
        handle_output(manager, b"Some text content\n")
        self.assertEqual(manager._last_accumulated_tokens, 150)

        # Test exception handling in log write
        with tempfile.TemporaryDirectory() as tmpdir:
            manager2 = self._create_mock_manager()
            manager2._project_root = pathlib.Path(tmpdir)
            # Don't create .agentflow dir, so parent check fails gracefully
            manager2._task_start_tokens = {"T-001": 50}
            handle_output(manager2, b"Output\nAGENTFLOW_TASK_COMPLETE:T-001\n")
            self.assertEqual(manager2._turn_count, 1)


    def test_handle_output_clear_with_manual_handoff_reset(self):
        """Clear command resets manual handoff flag."""
        manager = self._create_mock_manager()
        manager.session_type = "oracle"
        manager._manual_handoff = True

        chunk = b"/clear\n"
        handle_output(manager, chunk)

        self.assertFalse(manager._manual_handoff)
        # Check for manual_handoff_reset audit event
        audit_calls = [call[0][0] for call in manager._log_audit.call_args_list]
        self.assertTrue(any("manual_handoff_reset" in str(call) for call in audit_calls))

    def test_handle_output_clear_with_tokenizer_reset(self):
        """Clear command resets tokenizer if present and handles exceptions."""
        manager = self._create_mock_manager()
        manager.session_type = "oracle"
        manager._tokenizer.reset = Mock()
        manager._handoff_complete_path = pathlib.Path("/invalid/path/handoff.json")
        manager._state_machine.state = States.HANDOFF_PENDING

        chunk = b"/clear\nHANDOFF_COMPLETE\n"
        handle_output(manager, chunk)

        manager._tokenizer.reset.assert_called()
        # State transition should be called for HANDOFF_COMPLETE signal
        manager._state_machine.transition.assert_called()

    def test_handle_output_handoff_auto_trigger_conditions(self):
        """Auto handoff trigger requires task completion and no in-flight tasks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = self._create_mock_manager()
            project_root = pathlib.Path(tmpdir)
            manager._project_root = project_root
            agentflow_dir = project_root / ".agentflow"
            agentflow_dir.mkdir(parents=True, exist_ok=True)

            manager._manual_handoff = False
            manager._auto_handoff_disabled = Mock(return_value=False)
            manager._last_restart_ts = 0
            manager._config = {"handoff_primary_tokens": 100}
            manager._tokenizer.accumulate = Mock(return_value=120)
            manager._task_start_tokens = {}
            manager._state_machine.state = Mock()
            manager.trigger_handoff = Mock()

            # Task complete with total >= primary should trigger handoff
            chunk = b"Output\nAGENTFLOW_TASK_COMPLETE:T-001\n"
            handle_output(manager, chunk)

            # Verify trigger_handoff was called
            manager.trigger_handoff.assert_called_with(trigger="auto-primary")


    def test_handle_output_handoff_complete_signal(self):
        """HANDOFF_COMPLETE signal writes completion file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = self._create_mock_manager()
            manager._handoff_complete_path = pathlib.Path(tmpdir) / "handoff.json"
            manager._state_machine.state = States.HANDOFF_PENDING

            chunk = b"Processing\nHANDOFF_COMPLETE\n"
            handle_output(manager, chunk)

            # Verify state transition called
            manager._state_machine.transition.assert_called_with("handoff_complete_written")

if __name__ == "__main__":
    unittest.main()
