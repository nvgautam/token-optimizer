"""Tests for agentflow.shell.session_manager and agentflow.shell.countdown."""
from __future__ import annotations

import os
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
        self._on_exit = None
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

    def count_tokens(self, text: str, provider: str = "claude") -> int:
        """Pure token count — no side effects."""
        if self._fixed is not None:
            return self._fixed
        return 1  # 1 token per call

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
    assert sm._pending_banner.count("[IDX]") == 1, (
        f"Expected 1 IDX banner in pending, got: {sm._pending_banner!r}"
    )


def test_idx_banner_not_written_before_3_turns():
    sm, pty, _ = make_manager()
    for _ in range(2):
        fire_output(sm, pty, "content")
        fire_output(sm, pty, "\n\n")
    assert "[IDX]" not in sm._pending_banner


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


# ---------------------------------------------------------------------------
# T-010. Per-turn output token tracking + verbosity compliance signal
# ---------------------------------------------------------------------------


def test_output_tokens_reset_at_turn_boundary():
    """Per-turn token count is captured in history and counter restarts at boundary."""
    sm, pty, _ = make_manager()
    # Fire 3 content chunks so pre_boundary > 1 (boundary chunk contributes only 1)
    for _ in range(3):
        fire_output(sm, pty, "some response content")
    pre_boundary = sm._current_turn_output_tokens
    assert pre_boundary > 1
    fire_output(sm, pty, "\n\n")
    # turn tokens captured in history; counter restarted (only boundary chunk tokens remain)
    assert sm._turn_output_history == [pre_boundary]
    assert sm._current_turn_output_tokens < pre_boundary


def test_turn_output_history_appended_at_boundary():
    """Each turn's token count is appended to _turn_output_history."""
    sm, pty, _ = make_manager()
    for _ in range(3):
        fire_output(sm, pty, "response")
        fire_output(sm, pty, "\n\n")
    assert len(sm._turn_output_history) == 3


def test_turn_output_history_max_10():
    """_turn_output_history holds at most 10 entries."""
    sm, pty, _ = make_manager()
    for _ in range(15):
        fire_output(sm, pty, "response")
        fire_output(sm, pty, "\n\n")
    assert len(sm._turn_output_history) == 10


def test_verbosity_banner_injected_when_over_threshold():
    """Verbosity banner fires when turn output tokens exceed threshold."""
    sm, pty, _ = make_manager(config={"verbosity_threshold": 0})
    sm._verbosity_last_inject = 0.0  # push past the 30s cooldown guard
    fire_output(sm, pty, "some response content")
    fire_output(sm, pty, "\n\n")
    assert "[VERBOSITY]" in sm._pending_banner and "Last response:" in sm._pending_banner
    assert "tokens" in sm._pending_banner


def test_verbosity_banner_not_injected_when_under_threshold():
    """Verbosity banner is silent when turn output tokens are below threshold."""
    sm, pty, _ = make_manager(config={"verbosity_threshold": 9999})
    fire_output(sm, pty, "short")
    fire_output(sm, pty, "\n\n")
    assert not ("[VERBOSITY]" in sm._pending_banner and "Last response:" in sm._pending_banner)


def test_on_session_exit_writes_verbosity_log(tmp_path):
    """_on_session_exit writes per-turn stats to .agentflow/verbosity_log.jsonl."""
    import json
    import pathlib

    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    sm, pty, _ = make_manager()
    sm._turn_output_history = [10, 20, 30]
    sm.session_type = "oracle"

    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm._on_session_exit(0)

    log_path = agentflow_dir / "verbosity_log.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    records = [json.loads(line) for line in lines]
    assert records[0]["turn"] == 1
    assert records[0]["output_tokens"] == 10
    assert records[0]["session_type"] == "oracle"
    assert records[2]["turn"] == 3
    assert records[2]["output_tokens"] == 30


def test_on_session_exit_skips_when_no_agentflow_dir(tmp_path):
    """_on_session_exit does not create .agentflow/ if it does not exist."""
    import pathlib

    sm, pty, _ = make_manager()
    sm._turn_output_history = [5]

    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm._on_session_exit(0)  # must not raise

    assert not (tmp_path / ".agentflow").exists()


def test_on_session_exit_registered_on_pty():
    """_on_session_exit is registered as pty_wrapper._on_exit in __init__."""
    sm, pty, _ = make_manager()
    assert pty._on_exit == sm._on_session_exit


# ---------------------------------------------------------------------------
# T-052. Read-event idx injection + proactive verbosity banners
# ---------------------------------------------------------------------------


def test_ansi_strip_removes_sequences():
    """_ansi_strip removes standard ANSI escape sequences from text."""
    sm, pty, _ = make_manager()
    raw = "\x1b[32mGreen text\x1b[0m and \x1b[1mBold\x1b[0m"
    assert sm._ansi_strip(raw) == "Green text and Bold"


def test_ansi_strip_leaves_plain_text():
    """_ansi_strip does not modify text that contains no ANSI sequences."""
    sm, pty, _ = make_manager()
    plain = "Read tool agentflow/config/settings.py"
    assert sm._ansi_strip(plain) == plain


def test_detect_read_path_returns_path():
    """_detect_read_path extracts a file path when a Read pattern is present."""
    sm, pty, _ = make_manager()
    text = "Read tool agentflow/config/settings.py for configuration"
    result = sm._detect_read_path(text)
    assert result == "agentflow/config/settings.py"


def test_detect_read_path_keyword_arg_form():
    """_detect_read_path matches the Claude Code tool display format Read(file_path=...)."""
    sm, pty, _ = make_manager()
    text = 'Read(file_path="/Users/gautam/code/token-optimizer/design_status.md")'
    result = sm._detect_read_path(text)
    assert result == "/Users/gautam/code/token-optimizer/design_status.md"


def test_detect_read_path_positional_form():
    """_detect_read_path matches the positional form Read('/path/file.md')."""
    sm, pty, _ = make_manager()
    text = 'Read("/Users/gautam/code/token-optimizer/design_status.md")'
    result = sm._detect_read_path(text)
    assert result == "/Users/gautam/code/token-optimizer/design_status.md"


def test_detect_read_path_returns_none_when_absent():
    """_detect_read_path returns None when no Read pattern is present."""
    sm, pty, _ = make_manager()
    assert sm._detect_read_path("no read call here at all") is None


def test_detect_read_path_natural_language_returns_none():
    """Lowercase natural-language 'read the file.py' does not trigger idx injection."""
    sm, pty, _ = make_manager()
    assert sm._detect_read_path("read the config.py file for details") is None


def test_handle_output_injects_idx_banner_when_idx_exists(tmp_path):
    """_handle_output queues a targeted [IDX] banner when the .idx file exists."""
    sm, pty, _ = make_manager()
    idx_dir = tmp_path / ".agentflow" / "cache" / sm._cwd_hash / "index"
    (idx_dir / "agentflow" / "config").mkdir(parents=True)
    (idx_dir / "agentflow" / "config" / "settings.py.idx").touch()

    with patch("pathlib.Path.home", return_value=tmp_path):
        fire_output(sm, pty, "Read tool agentflow/config/settings.py to get config")

    assert "[IDX]" in sm._pending_banner and "exists" in sm._pending_banner


def test_handle_output_no_idx_banner_when_idx_absent(tmp_path):
    """_handle_output does not queue a targeted [IDX] banner when no .idx file found."""
    sm, pty, _ = make_manager()
    with patch("pathlib.Path.home", return_value=tmp_path):
        fire_output(sm, pty, "Read tool agentflow/config/settings.py to get config")

    assert not ("[IDX]" in sm._pending_banner and "exists" in sm._pending_banner)


def test_handle_output_injects_idx_banner_for_absolute_path(tmp_path):
    """Absolute paths inside cwd are stripped to relative before idx lookup."""
    sm, pty, _ = make_manager()
    idx_dir = tmp_path / ".agentflow" / "cache" / sm._cwd_hash / "index"
    (idx_dir / "agentflow" / "config").mkdir(parents=True)
    (idx_dir / "agentflow" / "config" / "settings.py.idx").touch()

    abs_path = os.path.join(os.getcwd(), "agentflow/config/settings.py")
    with patch("pathlib.Path.home", return_value=tmp_path):
        fire_output(sm, pty, f'Read("{abs_path}")')

    assert "[IDX]" in sm._pending_banner and "exists" in sm._pending_banner


def test_handle_output_no_idx_banner_for_path_outside_cwd(tmp_path):
    """Absolute paths outside the project root are silently ignored."""
    sm, pty, _ = make_manager()
    with patch("pathlib.Path.home", return_value=tmp_path):
        fire_output(sm, pty, 'Read("/etc/passwd")')

    assert not ("[IDX]" in sm._pending_banner and "exists" in sm._pending_banner)


def test_static_verbosity_banner_not_at_init():
    """Static verbosity banner must NOT be queued at __init__ time."""
    sm, pty, _ = make_manager()
    assert not ("[VERBOSITY]" in sm._pending_banner and "Target" in sm._pending_banner)


def test_static_verbosity_banner_not_before_quiet_period():
    """Static banner is not queued immediately after output (TUI still generating)."""
    sm, pty, _ = make_manager(config={"startup_quiet_period_seconds": 9999.0})
    fire_output(sm, pty, "x" * 2048)
    sm.on_idle_tick()
    assert not ("[VERBOSITY]" in sm._pending_banner and "Target" in sm._pending_banner)


def test_static_verbosity_banner_fires_after_quiet_period():
    """Static verbosity and IDX banners both queue once quiet period has elapsed."""
    sm, pty, _ = make_manager(config={"startup_quiet_period_seconds": 0.0})
    fire_output(sm, pty, "x" * 100)
    sm.on_idle_tick()
    assert "[VERBOSITY]" in sm._pending_banner and "Target" in sm._pending_banner
    assert "[IDX]" in sm._pending_banner and "grep" in sm._pending_banner


def test_static_verbosity_banner_fires_only_once():
    """Static banner queued exactly once regardless of repeated idle ticks."""
    sm, pty, _ = make_manager(config={"startup_quiet_period_seconds": 0.0})
    fire_output(sm, pty, "x" * 100)
    for _ in range(5):
        sm.on_idle_tick()
    assert sm._pending_banner.count("[VERBOSITY] Target") == 1



def test_every_3_turns_idx_injection_regression():
    """Generic every-3-turns IDX banner still queues alongside new Read-detection logic."""
    sm, pty, _ = make_manager()
    for _ in range(3):
        fire_output(sm, pty, "assistant response text")
        fire_output(sm, pty, "\n\n")
    # Generic banner contains "grep" (the lookup instruction); targeted banner does not
    assert "[IDX]" in sm._pending_banner and "grep" in sm._pending_banner
    assert sm._pending_banner.count("grep") == 1
