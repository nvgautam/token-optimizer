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
    # Pre-create .agentflow directory
    (tmp_path / ".agentflow").mkdir()

    pty = FakePTY()
    tok = FakeTokenizer()
    sm = SessionManager(pty, tok, config={})
    sm.session_type = "oracle"

    # Make the read_output call set _exited to True
    def mock_read_output(timeout=1.0):
        pty._exited = True
        return b"some output"
    pty.read_output = mock_read_output

    with patch.object(pathlib.Path, "cwd", return_value=tmp_path), \
         patch("agentflow.shell.session_manager.countdown") as mock_cd:
        sm.trigger_handoff(trigger="auto-safety")
        # Ensure countdown was NOT called (since handoff did not complete)
        mock_cd.assert_not_called()

    # Ensure handoff_aborted was logged with token count
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
    # Pre-create .agentflow directory
    (tmp_path / ".agentflow").mkdir()

    pty = FakePTY()
    tok = FakeTokenizer()
    sm = SessionManager(pty, tok, config={})
    sm.session_type = "oracle"

    outputs_to_return = [b"Chunk 1\n", b"HANDOFF_COMPLETE\n"]
    def mock_read_output(timeout=1.0):
        if outputs_to_return:
            return outputs_to_return.pop(0)
        return b""
    pty.read_output = mock_read_output

    with patch.object(pathlib.Path, "cwd", return_value=tmp_path), \
         patch("os.write") as mock_write, \
         patch("agentflow.shell.session_manager.countdown") as mock_cd:
        mock_cd.side_effect = lambda s, on_complete, **kw: on_complete()
        sm.trigger_handoff(trigger="auto-safety")

        # Verify os.write(1, ...) was called to forward output to stdout
        mock_write.assert_any_call(1, b"Chunk 1\n")
        mock_write.assert_any_call(1, b"HANDOFF_COMPLETE\n")
