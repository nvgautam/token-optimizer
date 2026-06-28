"""Tests for agentflow.shell.session_manager and agentflow.shell.countdown."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from agentflow.shell.session_manager import SessionManager
from agentflow.shell.countdown import countdown


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakePTY:
    """Minimal PTY wrapper stand-in."""

    def __init__(self):
        self._on_output = None
        self.inputs: list[str] = []

    def write_input(self, text: str) -> None:
        self.inputs.append(text)

    def read_output(self, timeout: float = 1.0) -> bytes:
        return b""


class FakeTokenizer:
    """Tokenizer mock with a controllable running total."""

    def __init__(self, fixed_return: int | None = None):
        self._total = 0
        self._fixed = fixed_return

    def accumulate(self, text: str, provider: str = "claude") -> int:
        if self._fixed is not None:
            return self._fixed
        self._total += 1  # 1 token per call — stays well below any threshold
        return self._total

    def reset(self) -> None:
        self._total = 0


def make_manager(config=None, tokenizer=None):
    pty = FakePTY()
    tok = tokenizer or FakeTokenizer()
    sm = SessionManager(pty, tok, config or {})
    return sm, pty, tok


def fire_output(sm: SessionManager, pty: FakePTY, text: str) -> None:
    """Deliver a simulated PTY output chunk to the registered callback."""
    if pty._on_output:
        pty._on_output(text.encode())


# ---------------------------------------------------------------------------
# 1. session_type set to "oracle" when /oracle detected
# ---------------------------------------------------------------------------


def test_session_type_oracle():
    sm, pty, _ = make_manager()
    fire_output(sm, pty, "/oracle\r\n")
    assert sm.session_type == "oracle"


# ---------------------------------------------------------------------------
# 2. session_type set to "orchestrator" when /orchestrate detected
# ---------------------------------------------------------------------------


def test_session_type_orchestrate():
    sm, pty, _ = make_manager()
    fire_output(sm, pty, "/orchestrate\r\n")
    assert sm.session_type == "orchestrator"


# ---------------------------------------------------------------------------
# 3. idx banner written via write_input every 3 turns
# ---------------------------------------------------------------------------


def test_idx_banner_every_3_turns():
    sm, pty, _ = make_manager()
    # Simulate 3 turns: non-empty content followed by blank line
    for _ in range(3):
        fire_output(sm, pty, "assistant response text")
        fire_output(sm, pty, "\n\n")
    banner_writes = [x for x in pty.inputs if "[IDX]" in x]
    assert len(banner_writes) == 1, f"Expected 1 banner, got {len(banner_writes)}"


def test_idx_banner_not_written_before_3_turns():
    sm, pty, _ = make_manager()
    for _ in range(2):
        fire_output(sm, pty, "content")
        fire_output(sm, pty, "\n\n")
    banner_writes = [x for x in pty.inputs if "[IDX]" in x]
    assert len(banner_writes) == 0


# ---------------------------------------------------------------------------
# 4. trigger_handoff() writes /handoff then /clear to pty_wrapper
# ---------------------------------------------------------------------------


def test_trigger_handoff_writes_commands():
    sm, pty, _ = make_manager()
    # Simulate immediate HANDOFF_COMPLETE response
    pty.read_output = lambda timeout=1.0: b"HANDOFF_COMPLETE\n"

    with patch("agentflow.shell.session_manager.countdown") as mock_cd:
        mock_cd.side_effect = lambda s, on_complete, **kw: on_complete()
        sm.trigger_handoff()

    assert "/handoff\n" in pty.inputs
    assert "/clear\n" in pty.inputs
    assert pty.inputs.index("/handoff\n") < pty.inputs.index("/clear\n")


# ---------------------------------------------------------------------------
# 5. threshold fires when tokenizer total exceeds oracle_threshold_tokens
# ---------------------------------------------------------------------------


def test_threshold_fires_for_oracle():
    tok = FakeTokenizer(fixed_return=61_000)  # always exceeds 60 000
    sm, pty, _ = make_manager(
        config={"oracle_threshold_tokens": 60_000},
        tokenizer=tok,
    )
    sm.session_type = "oracle"

    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "some output chunk")
        mock_hf.assert_called_once()


# ---------------------------------------------------------------------------
# 6. _manual_handoff flag suppresses auto-restart
# ---------------------------------------------------------------------------


def test_manual_handoff_suppresses_auto():
    tok = FakeTokenizer(fixed_return=61_000)
    sm, pty, _ = make_manager(
        config={"oracle_threshold_tokens": 60_000},
        tokenizer=tok,
    )
    sm.session_type = "oracle"
    sm._manual_handoff = True  # user already did /handoff

    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "some output chunk")
        mock_hf.assert_not_called()


# ---------------------------------------------------------------------------
# 7. countdown() prints per-second output and calls on_complete
# ---------------------------------------------------------------------------


def test_countdown_calls_on_complete():
    callback = MagicMock()
    with patch("agentflow.shell.countdown.time") as mock_time:
        mock_time.sleep = MagicMock()
        countdown(3, on_complete=callback)
    callback.assert_called_once()


def test_countdown_prints_per_second(capsys):
    callback = MagicMock()
    with patch("agentflow.shell.countdown.time") as mock_time:
        mock_time.sleep = MagicMock()
        countdown(3, on_complete=callback)
    err = capsys.readouterr().err
    assert "Restarting" in err
    assert "3s" in err


# ---------------------------------------------------------------------------
# 8. countdown() exits cleanly on KeyboardInterrupt
# ---------------------------------------------------------------------------


def test_countdown_keyboard_interrupt():
    callback = MagicMock()
    call_count = [0]

    def raising_sleep(n: float) -> None:
        call_count[0] += 1
        if call_count[0] == 1:
            raise KeyboardInterrupt

    with patch("agentflow.shell.countdown.time") as mock_time:
        mock_time.sleep = raising_sleep
        countdown(3, on_complete=callback)  # must not propagate the interrupt

    callback.assert_not_called()
