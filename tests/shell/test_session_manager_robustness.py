"""Tests for PTY session manager robustness and failure modes (T-117)."""
from __future__ import annotations
import json
import pathlib
from unittest.mock import MagicMock, patch
import pytest
from agentflow.shell.session_manager import SessionManager


class FakePTY:
    def __init__(self):
        self._exited = False
        self.inputs = []
        self._on_output = None
        self._on_exit = None

    def read_output(self, timeout=1.0):
        return b""

    def write_input(self, text):
        self.inputs.append(text)


class FakeTokenizer:
    def __init__(self):
        self._total = 0

    def count_tokens(self, text, provider="claude"):
        return 1

    def accumulate(self, text, provider="claude"):
        self._total += 1
        return self._total


def test_trigger_handoff_dead_pty_guard(tmp_path):
    """Dead PTY guard fires at trigger_handoff() entry, not inside removed loop."""
    (tmp_path / ".agentflow").mkdir()
    pty = FakePTY()
    tok = FakeTokenizer()
    sm = SessionManager(pty, tok, config={})
    sm.session_type = "oracle"
    # PTY is already dead before trigger_handoff is called
    pty._exited = True

    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm.trigger_handoff(trigger="auto-safety")

    log_path = tmp_path / ".agentflow" / "pty_audit.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    events = [json.loads(line) for line in lines]
    aborted_event = next(e for e in events if e.get("event") == "handoff_aborted")
    assert aborted_event["trigger"] == "auto-safety"
    assert aborted_event["tokens"] == 0


def test_trigger_handoff_write_input_oserror(tmp_path):
    # Pre-create .agentflow directory
    (tmp_path / ".agentflow").mkdir()

    pty = FakePTY()
    tok = FakeTokenizer()
    sm = SessionManager(pty, tok, config={})
    sm.session_type = "oracle"

    # write_input raises OSError
    def mock_write_input(text):
        raise OSError("PTY master fd is closed")
    pty.write_input = mock_write_input

    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        # Should not raise exception
        sm.trigger_handoff(trigger="auto-primary")

    log_path = tmp_path / ".agentflow" / "pty_audit.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    events = [json.loads(line) for line in lines]
    aborted_event = next(e for e in events if e.get("event") == "handoff_aborted")
    assert aborted_event["trigger"] == "auto-primary"


def test_trigger_handoff_output_forwarding(tmp_path):
    """After T-121, trigger_handoff no longer runs a blocking read loop.
    Output forwarding is handled by the main PTY event loop via poll_session.
    This test verifies that trigger_handoff transitions to HANDOFF_PENDING
    and poll_session picks up handoff_complete.json to advance state."""
    (tmp_path / ".agentflow").mkdir()
    pty = FakePTY()
    tok = FakeTokenizer()
    sm = SessionManager(pty, tok, config={})
    sm.session_type = "oracle"
    sm._project_root = tmp_path
    sm._handoff_complete_path = tmp_path / ".agentflow" / "handoff_complete.json"

    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm.trigger_handoff(trigger="auto-safety")
        assert sm._state_machine.state.name == "HANDOFF_PENDING"
        # Simulate handoff skill writing the completion file
        sm._handoff_complete_path.write_text("{}", encoding="utf-8")
        with patch.object(sm, "restart_child"):
            sm.poll()
        assert sm._state_machine.state.name == "RESTARTING"
