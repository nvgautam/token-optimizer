"""Tests for handoff auto-trigger and HANDOFF RECOMMENDED logic in handle_output."""
import unittest
from unittest.mock import Mock
import json
import pathlib
import tempfile

from agentflow.shell.output_handler import handle_output
from agentflow.shell.state_machine import States


class TestOutputHandlerHandoff(unittest.TestCase):
    """Handoff auto-trigger and HANDOFF RECOMMENDED signal tests."""

    def _create_mock_manager(self):
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
        manager._last_audit_token_bucket = 0
        return manager

    def test_handle_output_handoff_auto_trigger_conditions(self):
        """T-209: auto-primary output trigger removed — no trigger_handoff on task complete."""
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

            chunk = b"Output\nAGENTFLOW_TASK_COMPLETE:T-001\n"
            handle_output(manager, chunk)

            manager.trigger_handoff.assert_not_called()

    def test_auto_primary_no_trigger_for_orchestrate_session(self):
        """auto-primary handoff is suppressed for orchestrator session_type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = self._create_mock_manager()
            project_root = pathlib.Path(tmpdir)
            manager._project_root = project_root
            (project_root / ".agentflow").mkdir(parents=True, exist_ok=True)
            manager.session_type = "orchestrator"
            manager._manual_handoff = False
            manager._auto_handoff_disabled = Mock(return_value=False)
            manager._last_restart_ts = 0
            manager._config = {"handoff_primary_tokens": 100}
            manager._tokenizer.accumulate = Mock(return_value=120)
            manager._task_start_tokens = {}
            manager._state_machine.state = Mock()
            manager.trigger_handoff = Mock()

            handle_output(manager, b"Output\nAGENTFLOW_TASK_COMPLETE:T-001\n")

            manager.trigger_handoff.assert_not_called()

    def test_handle_output_handoff_complete_signal(self):
        """T-209: HANDOFF_COMPLETE text detection removed — no file write or transition on text."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = self._create_mock_manager()
            manager._handoff_complete_path = pathlib.Path(tmpdir) / "handoff.json"
            manager._state_machine.state = States.HANDOFF_PENDING

            chunk = b"Processing\nHANDOFF_COMPLETE\n"
            handle_output(manager, chunk)

            # Text scanning removed — file not written, no state transition triggered
            self.assertFalse(manager._handoff_complete_path.exists())
            assert not any(
                c == (("handoff_complete_written",), {})
                for c in manager._state_machine.transition.call_args_list
            )

    def test_handoff_recommended_evicts_completed_tasks(self):
        """T-209: HANDOFF RECOMMENDED output trigger removed — task tokens NOT evicted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            m = self._create_mock_manager()
            m._project_root = pathlib.Path(tmpdir)
            m._task_start_tokens = {"T-001": 1000}
            m._state_machine.state = States.IDLE
            (pathlib.Path(tmpdir) / "tasks.json").write_text(
                json.dumps({"tasks": [{"task_id": "T-001", "status": "complete"}]}))
            handle_output(m, b"HANDOFF RECOMMENDED\n")
            # T-209: eviction trigger removed; token tracking unchanged
            self.assertIn("T-001", m._task_start_tokens)

    def test_handoff_recommended_triggers_handoff_when_stalled(self):
        """T-209: HANDOFF RECOMMENDED stall-recovery trigger removed — no trigger_handoff call."""
        with tempfile.TemporaryDirectory() as tmpdir:
            m = self._create_mock_manager()
            m._project_root = pathlib.Path(tmpdir)
            m._task_start_tokens = {"T-001": 1000}
            m._config = {"handoff_primary_tokens": 100}
            m._tokenizer.accumulate = Mock(return_value=90000)
            m._state_machine.state = States.IDLE
            m.trigger_handoff = Mock()
            (pathlib.Path(tmpdir) / "tasks.json").write_text(
                json.dumps({"tasks": [{"task_id": "T-001", "status": "complete"}]}))
            handle_output(m, b"HANDOFF RECOMMENDED\n")
            m.trigger_handoff.assert_not_called()

    def test_handoff_recommended_skips_when_task_still_in_flight(self):
        """T-209: HANDOFF RECOMMENDED removed — no eviction or trigger regardless of in-flight."""
        with tempfile.TemporaryDirectory() as tmpdir:
            m = self._create_mock_manager()
            m._project_root = pathlib.Path(tmpdir)
            m._task_start_tokens = {"T-001": 1000, "T-002": 2000}
            m._config = {"handoff_primary_tokens": 100}
            m._tokenizer.accumulate = Mock(return_value=90000)
            m._state_machine.state = States.IDLE
            m.trigger_handoff = Mock()
            (pathlib.Path(tmpdir) / "tasks.json").write_text(json.dumps({"tasks": [
                {"task_id": "T-001", "status": "complete"},
                {"task_id": "T-002", "status": "pending"},
            ]}))
            handle_output(m, b"HANDOFF RECOMMENDED\n")
            # No eviction; no trigger
            self.assertIn("T-001", m._task_start_tokens)
            self.assertIn("T-002", m._task_start_tokens)
            m.trigger_handoff.assert_not_called()

    def test_handoff_recommended_no_trigger_for_orchestrate_session(self):
        """orchestrator session_type blocks handoff trigger even when stalled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            m = self._create_mock_manager()
            m._project_root = pathlib.Path(tmpdir)
            m.session_type = "orchestrator"
            m._task_start_tokens = {"T-001": 1000}
            m._config = {"handoff_primary_tokens": 100}
            m._tokenizer.accumulate = Mock(return_value=90000)
            m._state_machine.state = States.IDLE
            m.trigger_handoff = Mock()
            (pathlib.Path(tmpdir) / "tasks.json").write_text(
                json.dumps({"tasks": [{"task_id": "T-001", "status": "complete"}]}))
            handle_output(m, b"HANDOFF RECOMMENDED\n")
            m.trigger_handoff.assert_not_called()


if __name__ == "__main__":
    unittest.main()
