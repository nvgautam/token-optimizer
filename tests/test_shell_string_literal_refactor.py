"""Test suite for T-360: Replace raw string comparisons with helper methods.

Verifies that session_type checks in handoff_handler.py, threshold_sync.py, and
oracle_consent.py use is_oracle_session() and is_orchestrate_session() helpers.
"""
from __future__ import annotations

import pytest
from unittest.mock import Mock, patch, MagicMock
from agentflow.config.constants import (
    is_oracle_session,
    is_orchestrate_session,
    SESSION_TYPE_ORACLE,
    SESSION_TYPE_ORCHESTRATOR,
)


class TestHelperMethods:
    """Verify helper methods work correctly."""

    def test_is_oracle_session_true(self) -> None:
        """Test is_oracle_session returns True for oracle session type."""
        assert is_oracle_session(SESSION_TYPE_ORACLE) is True

    def test_is_oracle_session_false_on_orchestrator(self) -> None:
        """Test is_oracle_session returns False for orchestrator."""
        assert is_oracle_session(SESSION_TYPE_ORCHESTRATOR) is False

    def test_is_orchestrate_session_true(self) -> None:
        """Test is_orchestrate_session returns True for orchestrator."""
        assert is_orchestrate_session(SESSION_TYPE_ORCHESTRATOR) is True

    def test_is_orchestrate_session_false_on_oracle(self) -> None:
        """Test is_orchestrate_session returns False for oracle."""
        assert is_orchestrate_session(SESSION_TYPE_ORACLE) is False

    def test_helper_methods_with_literal_strings(self) -> None:
        """Test helpers work with literal strings (backward compatibility)."""
        assert is_oracle_session("oracle") is True
        assert is_orchestrate_session("orchestrator") is True
        assert is_oracle_session("orchestrator") is False
        assert is_orchestrate_session("oracle") is False


class TestThresholdSyncRefactored:
    """Verify threshold_sync.py uses helper methods."""

    def test_apply_session_threshold_oracle(self) -> None:
        """Test apply_session_threshold applies oracle threshold."""
        from agentflow.shell.threshold_sync import apply_session_threshold

        manager = Mock()
        manager.session_type = SESSION_TYPE_ORACLE
        manager._config = {"oracle_threshold_tokens": 50000}
        manager._state_machine = Mock()
        manager._state_machine.threshold_tokens = 0

        apply_session_threshold(manager)

        assert manager._state_machine.threshold_tokens == 50000

    def test_apply_session_threshold_orchestrator(self) -> None:
        """Test apply_session_threshold applies orchestrator threshold."""
        from agentflow.shell.threshold_sync import apply_session_threshold

        manager = Mock()
        manager.session_type = SESSION_TYPE_ORCHESTRATOR
        manager._config = {"handoff_primary_tokens": 80000}
        manager._state_machine = Mock()
        manager._state_machine.threshold_tokens = 0

        apply_session_threshold(manager)

        assert manager._state_machine.threshold_tokens == 80000

    def test_apply_session_threshold_unknown(self) -> None:
        """Test apply_session_threshold with unknown session type."""
        from agentflow.shell.threshold_sync import apply_session_threshold

        manager = Mock()
        manager.session_type = "unknown"
        manager._config = {}
        manager._state_machine = Mock()
        manager._state_machine.threshold_tokens = 0

        apply_session_threshold(manager)

        # Should not modify threshold for unknown session type
        assert manager._state_machine.threshold_tokens == 0


class TestOracleConsentRefactored:
    """Verify oracle_consent.py uses helper methods."""

    def test_is_oracle_idle_true(self) -> None:
        """Test _is_oracle_idle returns True for idle oracle session."""
        from agentflow.shell.oracle_consent import _is_oracle_idle
        from agentflow.shell.state_machine import States

        manager = Mock()
        manager.session_type = SESSION_TYPE_ORACLE
        manager._state_machine = Mock()
        manager._state_machine.state = States.IDLE

        assert _is_oracle_idle(manager) is True

    def test_is_oracle_idle_false_on_orchestrator(self) -> None:
        """Test _is_oracle_idle returns False for orchestrator."""
        from agentflow.shell.oracle_consent import _is_oracle_idle
        from agentflow.shell.state_machine import States

        manager = Mock()
        manager.session_type = SESSION_TYPE_ORCHESTRATOR
        manager._state_machine = Mock()
        manager._state_machine.state = States.IDLE

        assert _is_oracle_idle(manager) is False

    def test_on_enter_handoff_pending_oracle_confirmed(self) -> None:
        """Test on_enter_handoff_pending_oracle when consent confirmed."""
        from agentflow.shell.oracle_consent import on_enter_handoff_pending_oracle

        manager = Mock()
        manager._oracle_consent_confirmed = True
        manager.session_type = SESSION_TYPE_ORACLE
        manager._log_audit = Mock()

        result = on_enter_handoff_pending_oracle(manager)

        assert result is True

    def test_on_enter_handoff_pending_oracle_not_confirmed(self) -> None:
        """Test on_enter_handoff_pending_oracle when consent not confirmed."""
        from agentflow.shell.oracle_consent import on_enter_handoff_pending_oracle

        manager = Mock()
        manager._oracle_consent_confirmed = False
        manager.session_type = SESSION_TYPE_ORACLE

        result = on_enter_handoff_pending_oracle(manager)

        assert result is False

    def test_on_enter_handoff_pending_orchestrator(self) -> None:
        """Test on_enter_handoff_pending_oracle with orchestrator session type."""
        from agentflow.shell.oracle_consent import on_enter_handoff_pending_oracle

        manager = Mock()
        manager._oracle_consent_confirmed = True
        manager.session_type = SESSION_TYPE_ORCHESTRATOR

        result = on_enter_handoff_pending_oracle(manager)

        assert result is False

    def test_on_session_exit_oracle_conditions(self) -> None:
        """Test on_session_exit_oracle checks all conditions."""
        from agentflow.shell.oracle_consent import on_session_exit_oracle
        from agentflow.shell.state_machine import States
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = Mock()
            manager._oracle_consent_confirmed = True
            manager.session_type = SESSION_TYPE_ORACLE
            manager._state_machine = Mock()
            manager._state_machine.state = States.HANDOFF_PENDING
            manager._handoff_complete_path = Path(tmpdir) / "handoff_complete.json"
            manager._handoff_complete_path.write_text("{}")

            result = on_session_exit_oracle(manager)

            assert result is True

    def test_on_enter_restarting_oracle(self) -> None:
        """Test on_enter_restarting_oracle sets permission mode."""
        from agentflow.shell.oracle_consent import on_enter_restarting_oracle

        manager = Mock()
        manager._oracle_consent_confirmed = True
        manager.session_type = SESSION_TYPE_ORACLE
        manager._pty = Mock()
        manager._pty._command = ["claude"]
        manager._log_audit = Mock()

        on_enter_restarting_oracle(manager)

        # Verify command was updated with permission mode
        assert "--permission-mode" in manager._pty._command


class TestNoRawStringComparisons:
    """Verify no raw string comparisons remain in source files."""

    def test_handoff_handler_no_raw_strings(self) -> None:
        """Test that handoff_handler.py has no raw orchestrator/oracle strings."""
        from pathlib import Path

        handoff_file = Path(__file__).parent.parent / "agentflow" / "shell" / "handoff_handler.py"
        content = handoff_file.read_text()

        # Should not have raw string comparisons
        assert '== "orchestrator"' not in content
        assert '== "oracle"' not in content
        assert 'session_type == "' not in content

    def test_threshold_sync_no_raw_strings(self) -> None:
        """Test that threshold_sync.py has no raw orchestrator/oracle strings."""
        from pathlib import Path

        threshold_file = Path(__file__).parent.parent / "agentflow" / "shell" / "threshold_sync.py"
        content = threshold_file.read_text()

        # Should not have raw string comparisons
        assert '== "orchestrator"' not in content
        assert '== "oracle"' not in content
        assert 'in ("oracle", "orchestrator")' not in content

    def test_oracle_consent_no_raw_strings(self) -> None:
        """Test that oracle_consent.py has no raw orchestrator/oracle strings."""
        from pathlib import Path

        consent_file = Path(__file__).parent.parent / "agentflow" / "shell" / "oracle_consent.py"
        content = consent_file.read_text()

        # Should not have raw string comparisons
        assert '== "orchestrator"' not in content
        assert '== "oracle"' not in content
        assert 'session_type != "' not in content
