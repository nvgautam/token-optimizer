"""Tests for oracle session consent prompt and handoff UX (T-301)."""
from __future__ import annotations
import json
import os
import pathlib
import sys
from unittest.mock import MagicMock, patch, call
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from conftest import make_manager, FakePTY, FakeTokenizer

# Helpers

def _oracle_manager(tmp_path, threshold=90_000, tokens=0):
    """Return a manager set up as an oracle session at the given accumulated tokens."""
    tok = FakeTokenizer(fixed_return=tokens)
    sm, pty, _ = make_manager(
        config={"oracle_consent_threshold_tokens": threshold},
        tokenizer=tok,
    )
    sm._project_root = tmp_path
    (tmp_path / ".agentflow").mkdir(parents=True, exist_ok=True)
    sm.session_type = "oracle"
    sm._last_accumulated_tokens = tokens
    return sm, pty

# should_prompt_consent

def test_should_prompt_consent_oracle_at_threshold(tmp_path):
    from agentflow.shell.oracle_consent import should_prompt_consent
    sm, _ = _oracle_manager(tmp_path, threshold=90_000, tokens=90_000)
    assert should_prompt_consent(sm) is True


def test_should_prompt_consent_oracle_above_threshold(tmp_path):
    from agentflow.shell.oracle_consent import should_prompt_consent
    sm, _ = _oracle_manager(tmp_path, threshold=90_000, tokens=95_000)
    assert should_prompt_consent(sm) is True


def test_should_prompt_consent_oracle_below_threshold(tmp_path):
    from agentflow.shell.oracle_consent import should_prompt_consent
    sm, _ = _oracle_manager(tmp_path, threshold=90_000, tokens=80_000)
    assert should_prompt_consent(sm) is False


def test_should_prompt_consent_non_oracle(tmp_path):
    from agentflow.shell.oracle_consent import should_prompt_consent
    tok = FakeTokenizer(fixed_return=95_000)
    sm, _, _ = make_manager(config={"oracle_consent_threshold_tokens": 90_000}, tokenizer=tok)
    sm._project_root = tmp_path
    (tmp_path / ".agentflow").mkdir(parents=True, exist_ok=True)
    sm.session_type = "orchestrator"
    sm._last_accumulated_tokens = 95_000
    assert should_prompt_consent(sm) is False


def test_should_prompt_consent_no_session_type(tmp_path):
    from agentflow.shell.oracle_consent import should_prompt_consent
    sm, _ = _oracle_manager(tmp_path, threshold=90_000, tokens=95_000)
    sm.session_type = None
    assert should_prompt_consent(sm) is False


def test_should_prompt_consent_already_fired(tmp_path):
    from agentflow.shell.oracle_consent import should_prompt_consent
    sm, _ = _oracle_manager(tmp_path, threshold=90_000, tokens=95_000)
    sm._oracle_consent_fired = True
    assert should_prompt_consent(sm) is False


def test_should_prompt_consent_handoff_disabled(tmp_path):
    from agentflow.shell.oracle_consent import should_prompt_consent
    sm, _ = _oracle_manager(tmp_path, threshold=90_000, tokens=95_000)
    (tmp_path / ".agentflow" / "handoff_disabled").touch()
    assert should_prompt_consent(sm) is False


def test_should_prompt_consent_non_idle_state(tmp_path):
    from agentflow.shell.oracle_consent import should_prompt_consent
    from agentflow.shell.state_machine import States
    sm, _ = _oracle_manager(tmp_path, threshold=90_000, tokens=95_000)
    sm._state_machine.state = States.HANDOFF_PENDING
    assert should_prompt_consent(sm) is False


def test_should_prompt_consent_reads_fresh_context_fill(tmp_path):
    import time
    from agentflow.shell.oracle_consent import should_prompt_consent
    sm, _ = _oracle_manager(tmp_path, threshold=90_000, tokens=0)
    fill_file = tmp_path / ".agentflow" / "context_fill.json"
    fill_file.write_text(json.dumps({"fill_tokens": 95_000, "ts": time.time()}))
    assert should_prompt_consent(sm) is True


def test_should_prompt_consent_falls_back_on_stale_context_fill(tmp_path):
    import time
    from agentflow.shell.oracle_consent import should_prompt_consent
    sm, _ = _oracle_manager(tmp_path, threshold=90_000, tokens=80_000)
    fill_file = tmp_path / ".agentflow" / "context_fill.json"
    fill_file.write_text(json.dumps({"fill_tokens": 95_000, "ts": time.time() - 300}))
    assert should_prompt_consent(sm) is False

# inject_consent_prompt

def test_inject_consent_prompt_writes_to_child_stdin(tmp_path):
    from agentflow.shell.oracle_consent import inject_consent_prompt, _CONSENT_PROMPT
    sm, pty = _oracle_manager(tmp_path)
    with patch("os.write"):
        inject_consent_prompt(sm)
    assert any(_CONSENT_PROMPT in inp for inp in pty.inputs)


def test_inject_consent_prompt_writes_to_terminal(tmp_path):
    from agentflow.shell.oracle_consent import inject_consent_prompt, _CONSENT_PROMPT
    sm, pty = _oracle_manager(tmp_path)
    written = []
    with patch("os.write", side_effect=lambda fd, data: written.append((fd, data))):
        inject_consent_prompt(sm)
    terminal_writes = [d for fd, d in written if fd == 1]
    assert any(_CONSENT_PROMPT.encode() in d for d in terminal_writes)


def test_inject_consent_prompt_sets_flags(tmp_path):
    from agentflow.shell.oracle_consent import inject_consent_prompt
    sm, pty = _oracle_manager(tmp_path)
    with patch("os.write"):
        inject_consent_prompt(sm)
    assert sm._oracle_consent_pending is True
    assert sm._oracle_consent_fired is True


def test_inject_consent_prompt_pty_error_does_not_raise(tmp_path):
    from agentflow.shell.oracle_consent import inject_consent_prompt
    sm, pty = _oracle_manager(tmp_path)
    pty.write_input = MagicMock(side_effect=OSError("pty gone"))
    with patch("os.write"):
        inject_consent_prompt(sm)  # Should not raise
    # flags not set when pty write fails
    assert sm._oracle_consent_pending is False

# check_oracle_consent_threshold

def test_check_oracle_consent_threshold_triggers_at_threshold(tmp_path):
    from agentflow.shell.oracle_consent import check_oracle_consent_threshold, _CONSENT_PROMPT
    sm, pty = _oracle_manager(tmp_path, threshold=90_000, tokens=90_000)
    with patch("os.write"):
        check_oracle_consent_threshold(sm)
    assert any(_CONSENT_PROMPT in inp for inp in pty.inputs)


def test_check_oracle_consent_threshold_no_trigger_below(tmp_path):
    from agentflow.shell.oracle_consent import check_oracle_consent_threshold
    sm, pty = _oracle_manager(tmp_path, threshold=90_000, tokens=80_000)
    with patch("os.write"):
        check_oracle_consent_threshold(sm)
    assert pty.inputs == []


def test_check_oracle_consent_threshold_no_retrigger(tmp_path):
    from agentflow.shell.oracle_consent import check_oracle_consent_threshold, _CONSENT_PROMPT
    sm, pty = _oracle_manager(tmp_path, threshold=90_000, tokens=95_000)
    with patch("os.write"):
        check_oracle_consent_threshold(sm)
        check_oracle_consent_threshold(sm)  # second call
    # prompt only injected once
    consent_writes = [inp for inp in pty.inputs if _CONSENT_PROMPT in inp]
    assert len(consent_writes) == 1

# check_oracle_consent_output

def test_check_oracle_consent_output_no_op_when_not_pending(tmp_path):
    from agentflow.shell.oracle_consent import check_oracle_consent_output
    sm, pty = _oracle_manager(tmp_path)
    sm._oracle_consent_pending = False
    with patch.object(sm, "trigger_handoff") as mock_trigger:
        check_oracle_consent_output(sm, b"some output")
        mock_trigger.assert_not_called()


def test_check_oracle_consent_output_triggers_on_handoff_complete(tmp_path):
    from agentflow.shell.oracle_consent import check_oracle_consent_output
    sm, pty = _oracle_manager(tmp_path)
    sm._oracle_consent_pending = True
    # Write handoff_complete file
    hc_path = sm._handoff_complete_path
    hc_path.parent.mkdir(parents=True, exist_ok=True)
    hc_path.write_text(json.dumps({"status": "complete"}))
    with patch.object(sm, "trigger_handoff") as mock_trigger:
        check_oracle_consent_output(sm, b"HANDOFF_COMPLETE: .agentflow/handoff_2026-07-20.md")
        mock_trigger.assert_called_once_with(trigger="oracle_consent")
    assert sm._oracle_consent_confirmed is True
    assert sm._oracle_consent_pending is False


def test_check_oracle_consent_output_no_trigger_without_file(tmp_path):
    from agentflow.shell.oracle_consent import check_oracle_consent_output
    sm, pty = _oracle_manager(tmp_path)
    sm._oracle_consent_pending = True
    # No handoff_complete file
    with patch.object(sm, "trigger_handoff") as mock_trigger:
        check_oracle_consent_output(sm, b"some regular oracle output")
        mock_trigger.assert_not_called()
    assert sm._oracle_consent_confirmed is False


def test_check_oracle_consent_output_no_double_trigger(tmp_path):
    from agentflow.shell.oracle_consent import check_oracle_consent_output
    sm, pty = _oracle_manager(tmp_path)
    sm._oracle_consent_pending = True
    sm._oracle_consent_confirmed = True  # already confirmed
    hc_path = sm._handoff_complete_path
    hc_path.parent.mkdir(parents=True, exist_ok=True)
    hc_path.write_text(json.dumps({"status": "complete"}))
    with patch.object(sm, "trigger_handoff") as mock_trigger:
        check_oracle_consent_output(sm, b"output")
        mock_trigger.assert_not_called()

# on_enter_handoff_pending_oracle

def test_on_enter_handoff_pending_oracle_skips_when_confirmed(tmp_path):
    from agentflow.shell.oracle_consent import on_enter_handoff_pending_oracle
    sm, pty = _oracle_manager(tmp_path)
    sm._oracle_consent_confirmed = True
    result = on_enter_handoff_pending_oracle(sm)
    assert result is True
    # /handoff should NOT have been written to pty
    assert "/handoff" not in " ".join(pty.inputs)


def test_on_enter_handoff_pending_oracle_normal_when_not_confirmed(tmp_path):
    from agentflow.shell.oracle_consent import on_enter_handoff_pending_oracle
    sm, pty = _oracle_manager(tmp_path)
    sm._oracle_consent_confirmed = False
    result = on_enter_handoff_pending_oracle(sm)
    assert result is False


def test_on_enter_handoff_pending_oracle_false_for_non_oracle(tmp_path):
    from agentflow.shell.oracle_consent import on_enter_handoff_pending_oracle
    sm, pty = _oracle_manager(tmp_path)
    sm.session_type = "orchestrator"
    sm._oracle_consent_confirmed = True
    result = on_enter_handoff_pending_oracle(sm)
    assert result is False

# on_session_exit_oracle

def test_on_session_exit_oracle_allows_restart_when_confirmed(tmp_path):
    from agentflow.shell.oracle_consent import on_session_exit_oracle
    from agentflow.shell.state_machine import States
    sm, pty = _oracle_manager(tmp_path)
    sm._oracle_consent_confirmed = True
    sm._state_machine.state = States.HANDOFF_PENDING
    hc_path = sm._handoff_complete_path
    hc_path.parent.mkdir(parents=True, exist_ok=True)
    hc_path.write_text(json.dumps({"status": "complete"}))
    with patch.object(sm._state_machine, "transition") as mock_tr:
        result = on_session_exit_oracle(sm)
    assert result is True
    mock_tr.assert_called_once_with("handoff_complete_written")


def test_on_session_exit_oracle_false_without_confirmation(tmp_path):
    from agentflow.shell.oracle_consent import on_session_exit_oracle
    from agentflow.shell.state_machine import States
    sm, pty = _oracle_manager(tmp_path)
    sm._oracle_consent_confirmed = False
    sm._state_machine.state = States.HANDOFF_PENDING
    hc_path = sm._handoff_complete_path
    hc_path.parent.mkdir(parents=True, exist_ok=True)
    hc_path.write_text(json.dumps({"status": "complete"}))
    result = on_session_exit_oracle(sm)
    assert result is False


def test_on_session_exit_oracle_false_for_non_oracle(tmp_path):
    from agentflow.shell.oracle_consent import on_session_exit_oracle
    from agentflow.shell.state_machine import States
    sm, pty = _oracle_manager(tmp_path)
    sm.session_type = "orchestrator"
    sm._oracle_consent_confirmed = True
    sm._state_machine.state = States.HANDOFF_PENDING
    hc_path = sm._handoff_complete_path
    hc_path.parent.mkdir(parents=True, exist_ok=True)
    hc_path.write_text(json.dumps({"status": "complete"}))
    result = on_session_exit_oracle(sm)
    assert result is False

# on_enter_restarting_oracle

def test_on_enter_restarting_oracle_adds_auto_mode(tmp_path):
    from agentflow.shell.oracle_consent import on_enter_restarting_oracle
    sm, pty = _oracle_manager(tmp_path)
    sm._oracle_consent_confirmed = True
    pty._command = ["claude"]
    on_enter_restarting_oracle(sm)
    assert "--permission-mode" in pty._command
    assert "auto" in pty._command


def test_on_enter_restarting_oracle_no_op_for_non_oracle(tmp_path):
    from agentflow.shell.oracle_consent import on_enter_restarting_oracle
    sm, pty = _oracle_manager(tmp_path)
    sm.session_type = "orchestrator"
    sm._oracle_consent_confirmed = True
    pty._command = ["claude"]
    on_enter_restarting_oracle(sm)
    assert "--permission-mode" not in pty._command


def test_on_enter_restarting_oracle_no_op_when_not_confirmed(tmp_path):
    from agentflow.shell.oracle_consent import on_enter_restarting_oracle
    sm, pty = _oracle_manager(tmp_path)
    sm._oracle_consent_confirmed = False
    pty._command = ["claude"]
    on_enter_restarting_oracle(sm)
    assert "--permission-mode" not in pty._command


def test_on_enter_restarting_oracle_idempotent(tmp_path):
    from agentflow.shell.oracle_consent import on_enter_restarting_oracle
    sm, pty = _oracle_manager(tmp_path)
    sm._oracle_consent_confirmed = True
    pty._command = ["claude", "--permission-mode", "auto"]
    on_enter_restarting_oracle(sm)
    # Should not double-add
    assert pty._command.count("--permission-mode") == 1


