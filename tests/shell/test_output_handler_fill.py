"""Tests for fill-token-based threshold guard and audit gate in handle_output."""
import unittest
from unittest.mock import Mock
import json
import pathlib
import tempfile
import time

from agentflow.shell.output_handler import handle_output
from agentflow.shell.state_machine import States


class TestFillTokenGuard(unittest.TestCase):
    """Tests for fill-token-based threshold guard in handle_output."""

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
        manager._state_machine.state = States.IDLE
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
        manager.trigger_handoff = Mock()
        manager._last_audit_token_bucket = 0
        return manager

    def test_handle_output_uses_fill_tokens_when_fresh(self):
        """Fresh context_fill.json with fill >= 70% of window triggers handoff."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = self._create_mock_manager()
            project_root = pathlib.Path(tmpdir)
            manager._project_root = project_root
            agentflow_dir = project_root / ".agentflow"
            agentflow_dir.mkdir(parents=True, exist_ok=True)

            # fill = 140001 > 70% of 200000; accumulate is well below primary
            fill_data = {"fill_tokens": 140001, "ts": time.time()}
            (agentflow_dir / "context_fill.json").write_text(
                json.dumps(fill_data), encoding="utf-8"
            )

            manager._config = {"handoff_primary_tokens": 80000}
            # accumulate returns 50000 — below primary, so fallback would NOT trigger
            manager._tokenizer.accumulate = Mock(return_value=50000)
            manager.session_type = "oracle"
            manager._task_start_tokens = {}

            handle_output(manager, b"Output\nAGENTFLOW_TASK_COMPLETE:T-001\n")

            manager.trigger_handoff.assert_called_with(trigger="auto-primary")

    def test_handle_output_falls_back_to_terminal_count_when_stale(self):
        """Stale context_fill.json causes fallback to total >= primary check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = self._create_mock_manager()
            project_root = pathlib.Path(tmpdir)
            manager._project_root = project_root
            agentflow_dir = project_root / ".agentflow"
            agentflow_dir.mkdir(parents=True, exist_ok=True)

            # Stale fill: ts is 120 seconds ago
            fill_data = {"fill_tokens": 150000, "ts": time.time() - 120}
            (agentflow_dir / "context_fill.json").write_text(
                json.dumps(fill_data), encoding="utf-8"
            )

            manager._config = {"handoff_primary_tokens": 80000}
            # accumulate returns 90000 >= primary=80000 → fallback should trigger
            manager._tokenizer.accumulate = Mock(return_value=90000)
            manager.session_type = "oracle"
            manager._task_start_tokens = {}

            handle_output(manager, b"Output\nAGENTFLOW_TASK_COMPLETE:T-001\n")

            manager.trigger_handoff.assert_called_with(trigger="auto-primary")

    def test_handle_output_token_evaluation_gated(self):
        """Token evaluation audit only fires at 10K-token bucket boundaries, not every chunk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = self._create_mock_manager()
            project_root = pathlib.Path(tmpdir)
            manager._project_root = project_root
            (project_root / ".agentflow").mkdir(parents=True, exist_ok=True)

            manager._config = {"handoff_primary_tokens": 80000}
            manager.session_type = "oracle"
            manager._task_start_tokens = {}
            manager._last_audit_token_bucket = 0

            # First call: total = 5000 — below first 10K boundary, no audit
            manager._tokenizer.accumulate = Mock(return_value=5000)
            handle_output(manager, b"chunk one\n")

            # Second call: total = 11000 — crosses first 10K boundary, audit fires
            manager._tokenizer.accumulate = Mock(return_value=11000)
            handle_output(manager, b"chunk two\n")

            # Third call: total = 12000 — same bucket (1), no additional audit
            manager._tokenizer.accumulate = Mock(return_value=12000)
            handle_output(manager, b"chunk three\n")

            audit_calls = [call[0][0] for call in manager._log_audit.call_args_list]
            token_eval_calls = [c for c in audit_calls if c.get("event") == "token_evaluation"]
            assert len(token_eval_calls) == 1, f"Expected 1 token_evaluation audit, got {len(token_eval_calls)}"
            assert token_eval_calls[0]["accumulated_tokens"] == 11000


if __name__ == "__main__":
    unittest.main()
