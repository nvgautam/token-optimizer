"""Tests for handoff and trigger logic in agentflow.shell.session_manager."""
from __future__ import annotations
import json
import pathlib
import sys
import time
from unittest.mock import MagicMock, patch
import pytest
from agentflow.shell.session_manager import SessionManager

# Make conftest importable
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from conftest import make_manager, fire_output, FakePTY, FakeTokenizer


def test_trigger_handoff_writes_commands(tmp_path):
    sm, pty, _ = make_manager()
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        original_write = pty.write_input
        def mock_write_input(text):
            original_write(text)
            if "/handoff" in text:
                sm._handoff_complete_path.parent.mkdir(parents=True, exist_ok=True)
                sm._handoff_complete_path.write_text("{}", encoding="utf-8")
        pty.write_input = mock_write_input
        with patch("agentflow.shell.session_manager.countdown") as mock_cd:
            mock_cd.side_effect = lambda s, on_complete, **kw: on_complete()
            sm.trigger_handoff()
    assert "/handoff\r" in pty.inputs  # T-148: PTY expects \r not \n

def test_safety_and_ceiling_triggers_removed():
    """T-151: safety (120K) and ceiling (150K) triggers no longer fire."""
    # 121K tokens — old safety trigger; must NOT fire without task_just_completed
    tok = FakeTokenizer(fixed_return=121_000)
    sm, pty, _ = make_manager(config={"handoff_primary_tokens": 80_000}, tokenizer=tok)
    sm.session_type = "oracle"
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "some output chunk")
        mock_hf.assert_not_called()

    # 151K tokens — old ceiling trigger; must NOT fire without task_just_completed
    tok2 = FakeTokenizer(fixed_return=151_000)
    sm2, pty2, _ = make_manager(config={"handoff_primary_tokens": 80_000}, tokenizer=tok2)
    sm2.session_type = "oracle"
    with patch.object(sm2, "trigger_handoff") as mock_hf:
        fire_output(sm2, pty2, "some output chunk")
        mock_hf.assert_not_called()

    # manual_handoff suppresses primary trigger
    tok3 = FakeTokenizer(fixed_return=85_000)
    sm3, pty3, _ = make_manager(config={"handoff_primary_tokens": 80_000}, tokenizer=tok3)
    sm3.session_type = "oracle"
    sm3._manual_handoff = True
    with patch.object(sm3, "trigger_handoff") as mock_hf:
        fire_output(sm3, pty3, "AGENTFLOW_TASK_COMPLETE:T-001")
        mock_hf.assert_not_called()

def test_primary_triggers():
    # T-209: auto-primary output trigger removed — oracle sessions use file-based path
    tok = FakeTokenizer(fixed_return=85_000)
    sm, pty, _ = make_manager(config={"handoff_primary_tokens": 80_000}, tokenizer=tok)
    sm.session_type = "oracle"
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-001")
        mock_hf.assert_not_called()

def test_orchestrator_never_triggers_auto_primary():
    # Orchestrator sessions are excluded from auto-primary handoff (they manage
    # their own context lifecycle via handoff_complete.json).
    tok = FakeTokenizer(fixed_return=85_000)
    sm, pty, _ = make_manager(config={"handoff_primary_tokens": 80_000}, tokenizer=tok)
    sm.session_type = "orchestrator"
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-001")
        mock_hf.assert_not_called()

def test_primary_suppressed_cases():
    tok = FakeTokenizer(fixed_return=85_000)
    sm, pty, _ = make_manager(config={"handoff_primary_tokens": 80_000}, tokenizer=tok)
    sm.session_type = "oracle"
    # Task in-flight suppresses even when task_just_completed signal present
    sm._task_start_tokens["T-002"] = 40_000
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-001")
        mock_hf.assert_not_called()
    # Below primary threshold — no trigger
    tok._fixed = 50_000
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-001")
        mock_hf.assert_not_called()
    # No task_just_completed signal — no trigger even above threshold
    tok._fixed = 85_000
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "some regular output")
        mock_hf.assert_not_called()

def test_pty_audit_logging(tmp_path):
    """Audit log captures handoff and restart events; T-209 removed output-based triggers."""
    (tmp_path / ".agentflow").mkdir()
    tok = FakeTokenizer(fixed_return=100)
    sm, pty, _ = make_manager(config={"handoff_primary_tokens": 80_000}, tokenizer=tok)
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm._project_root = tmp_path
        sm._task_complete_path = tmp_path / ".agentflow" / "task_complete.json"
        sm._handoff_complete_path = tmp_path / ".agentflow" / "handoff_complete.json"
        fire_output(sm, pty, "/oracle\r\n")
        # T-209: auto-primary output trigger removed — no trigger_handoff from handle_output
        tok._fixed, sm.session_type = 85_000, "oracle"
        with patch.object(sm, "trigger_handoff") as mock_hf:
            fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-999")
            mock_hf.assert_not_called()
        with patch("agentflow.shell.session_manager.countdown") as mock_cd, \
             patch.object(sm, "_spawn_new_child"):
            mock_cd.side_effect = lambda s, on_complete, **kw: on_complete()
            sm._force_async_handoff = True
            # trigger_handoff logs trigger_handoff + manual_handoff_set events
            sm.trigger_handoff(trigger="manual")
            # Write clear_signal file so clear_detected + session_type_transition fire
            (tmp_path / ".agentflow" / "clear_signal").touch()
            fire_output(sm, pty, "some output after clear\n")
            (tmp_path / ".agentflow" / "handoff_complete.json").write_text("{}", encoding="utf-8")
            sm.poll()
            sm.trigger_handoff(trigger="auto")
            sm.poll()
    log_path = tmp_path / ".agentflow" / "pty_audit.jsonl"
    assert log_path.exists()
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").strip().split("\n")]
    event_names = [e["event"] for e in events]
    # T-209: token_evaluation removed; other audit events still fire
    for ev in ["manual_handoff_set", "clear_detected", "session_type_transition", "trigger_handoff", "restart_session"]:
        assert ev in event_names, f"Expected event '{ev}' in {event_names}"

def test_async_trigger_handoff_success(tmp_path):
    sm, pty, _ = make_manager()
    sm._force_async_handoff = True
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm._project_root = tmp_path
        sm._task_complete_path = tmp_path / ".agentflow" / "task_complete.json"
        sm._handoff_complete_path = tmp_path / ".agentflow" / "handoff_complete.json"
        t0 = time.monotonic()
        with patch("agentflow.shell.session_manager.countdown") as mock_cd:
            mock_cd.side_effect = lambda s, on_complete, **kw: on_complete()
            sm.trigger_handoff()
            assert time.monotonic() - t0 < 0.5 and sm._handoff_in_progress is True
            sm._handoff_complete_path.parent.mkdir(parents=True, exist_ok=True)
            sm._handoff_complete_path.write_text("{}", encoding="utf-8")
            sm.poll()
    assert sm._handoff_in_progress is False
    assert "/handoff\r" in pty.inputs  # T-148: PTY expects \r not \n

def test_async_trigger_handoff_unexpected_exit(tmp_path):
    sm, pty, _ = make_manager()
    sm._force_async_handoff = True
    pty._exited = True
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm._project_root = tmp_path
        sm._handoff_complete_path = tmp_path / ".agentflow" / "handoff_complete.json"
        with patch("agentflow.shell.session_manager.countdown") as mock_cd:
            sm.trigger_handoff()
            mock_cd.assert_not_called()
    assert sm._handoff_in_progress is False

def test_async_trigger_handoff_oserror(tmp_path):
    sm, pty, _ = make_manager()
    sm._force_async_handoff = True
    def failing_write_input(text):
        raise OSError("closed")
    pty.write_input = failing_write_input
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm._project_root = tmp_path
        sm._handoff_complete_path = tmp_path / ".agentflow" / "handoff_complete.json"
        sm.trigger_handoff()
    assert sm._handoff_in_progress is False

def test_manual_handoff_reset_on_clear(tmp_path):
    (tmp_path / ".agentflow").mkdir()
    sm, pty, _ = make_manager()
    sm._project_root = tmp_path
    sm._manual_handoff = True
    (tmp_path / ".agentflow" / "clear_signal").touch()
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        fire_output(sm, pty, "chunk to trigger output processing")
    assert sm._manual_handoff is False

def test_tokenizer_resets_on_clear_prevents_rehangoff(tmp_path):
    """T-151: after /clear the tokenizer resets; subsequent primary trigger
    should not fire because accumulated count is now 0 (below 80K)."""
    class PreloadedTokenizer(FakeTokenizer):
        def __init__(self, seed: int):
            super().__init__()
            self._total = seed
        def accumulate(self, text, provider="claude"):
            self._total += 1
            return self._total
        def reset(self):
            self._total = 0
    # Seed above primary threshold; /clear must reset so no re-trigger fires
    tok = PreloadedTokenizer(seed=90_000)
    sm, pty, _ = make_manager(config={"handoff_primary_tokens": 80_000}, tokenizer=tok)
    sm.session_type = "oracle"
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        with patch.object(sm, "trigger_handoff") as mock_hf:
            fire_output(sm, pty, "/clear\n")
            # Post-clear: tokenizer._total == 0; send task_complete — below 80K, no trigger
            fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-001")
            mock_hf.assert_not_called()


# ---------------------------------------------------------------------------
# T-159: orchestrate session_type branch
# ---------------------------------------------------------------------------

def test_orchestrator_handoff_pending_skips_slash_handoff(tmp_path):
    """Orchestrate sessions must NOT inject /handoff — write handoff_complete.json directly."""
    sm, pty, _ = make_manager()
    sm.session_type = "orchestrator"
    sm._handoff_complete_path = tmp_path / ".agentflow" / "handoff_complete.json"
    from agentflow.shell.handoff_handler import handle_enter_handoff_pending
    handle_enter_handoff_pending(sm)
    assert "/handoff\r" not in pty.inputs, "PTY must not receive /handoff for orchestrator"
    assert sm._handoff_complete_path.exists(), "handoff_complete.json must be written directly"
    data = json.loads(sm._handoff_complete_path.read_text())
    assert data["source"] == "direct"


def test_oracle_handoff_pending_injects_slash_handoff(tmp_path):
    """Oracle sessions must still inject /handoff\\r into the PTY."""
    sm, pty, _ = make_manager()
    sm.session_type = "oracle"
    sm._handoff_complete_path = tmp_path / ".agentflow" / "handoff_complete.json"
    from agentflow.shell.handoff_handler import handle_enter_handoff_pending
    handle_enter_handoff_pending(sm)
    assert "/handoff\r" in pty.inputs


def test_none_session_type_handoff_pending_injects_slash_handoff(tmp_path):
    """Unknown/None session_type falls back to the /handoff LLM skill path."""
    sm, pty, _ = make_manager()
    sm.session_type = None
    sm._handoff_complete_path = tmp_path / ".agentflow" / "handoff_complete.json"
    from agentflow.shell.handoff_handler import handle_enter_handoff_pending
    handle_enter_handoff_pending(sm)
    assert "/handoff\r" in pty.inputs


def test_orchestrator_handoff_complete_json_content(tmp_path):
    """handoff_complete.json written by orchestrator path has status=complete."""
    sm, pty, _ = make_manager()
    sm.session_type = "orchestrator"
    sm._handoff_complete_path = tmp_path / ".agentflow" / "handoff_complete.json"
    from agentflow.shell.handoff_handler import handle_enter_handoff_pending
    handle_enter_handoff_pending(sm)
    data = json.loads(sm._handoff_complete_path.read_text())
    assert data["status"] == "complete"


# ---------------------------------------------------------------------------
# T-212: oracle sessions must NOT restart after handoff
# ---------------------------------------------------------------------------

def test_oracle_session_exit_does_not_restart(tmp_path):
    """T-212: oracle sessions must exit cleanly — no restart after handoff_complete.json."""
    from agentflow.shell.session_manager_handlers import handle_session_exit
    from agentflow.shell.state_machine import States

    sm, pty, _ = make_manager()
    sm.session_type = "oracle"
    sm._handoff_complete_path = tmp_path / ".agentflow" / "handoff_complete.json"
    sm._handoff_complete_path.parent.mkdir(parents=True, exist_ok=True)
    sm._handoff_complete_path.write_text("{}", encoding="utf-8")

    sm._state_machine.transition("trigger_handoff")  # → HANDOFF_PENDING
    assert sm._state_machine.state == States.HANDOFF_PENDING

    transitions = []
    original = sm._state_machine.transition
    def capture(name, **kw):
        transitions.append(name)
        return original(name, **kw)
    sm._state_machine.transition = capture

    handle_session_exit(sm, exit_code=0)

    assert "handoff_complete_written" not in transitions, "oracle must not trigger restart"
    assert "pty_eof" in transitions


def test_orchestrator_session_exit_restarts(tmp_path):
    """T-212: orchestrator sessions still restart via handoff_complete_written."""
    from agentflow.shell.session_manager_handlers import handle_session_exit
    from agentflow.shell.state_machine import States

    sm, pty, _ = make_manager()
    sm.session_type = "orchestrator"
    sm._handoff_complete_path = tmp_path / ".agentflow" / "handoff_complete.json"
    sm._handoff_complete_path.parent.mkdir(parents=True, exist_ok=True)
    sm._handoff_complete_path.write_text("{}", encoding="utf-8")

    sm._state_machine.transition("trigger_handoff")  # → HANDOFF_PENDING
    assert sm._state_machine.state == States.HANDOFF_PENDING

    transitions = []
    original = sm._state_machine.transition
    def capture(name, **kw):
        transitions.append(name)
        return original(name, **kw)
    sm._state_machine.transition = capture

    handle_session_exit(sm, exit_code=0)

    assert "handoff_complete_written" in transitions
