"""Tests for T-265: _handoff_in_progress is read-only property."""
from __future__ import annotations
from unittest.mock import Mock
import pytest

from agentflow.shell.session_manager import SessionManager
from agentflow.shell.state_machine import States


class TestHandoffInProgressReadOnly:
    """T-265: _handoff_in_progress property must be read-only."""

    def test_handoff_in_progress_getter_works(self):
        """Reading _handoff_in_progress should return boolean based on state machine."""
        mock_pty = Mock()
        mock_tokenizer = Mock()
        manager = SessionManager(mock_pty, mock_tokenizer, {})

        # When state is IDLE, should return False
        manager._state_machine.state = States.IDLE
        assert manager._handoff_in_progress is False

        # When state is HANDOFF_PENDING, should return True
        manager._state_machine.state = States.HANDOFF_PENDING
        assert manager._handoff_in_progress is True

        # When state is RESTARTING, should return True
        manager._state_machine.state = States.RESTARTING
        assert manager._handoff_in_progress is True

    def test_handoff_in_progress_setter_raises_attribute_error(self):
        """Assigning to _handoff_in_progress should raise AttributeError."""
        mock_pty = Mock()
        mock_tokenizer = Mock()
        manager = SessionManager(mock_pty, mock_tokenizer, {})

        # Try to set to False
        with pytest.raises(AttributeError):
            manager._handoff_in_progress = False

        # Try to set to True
        with pytest.raises(AttributeError):
            manager._handoff_in_progress = True
