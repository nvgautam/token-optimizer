"""Tests for agentflow.shell.session_manager and agentflow.shell.countdown."""
from __future__ import annotations
import json
import pathlib
import time
from unittest.mock import MagicMock, patch
import pytest
from agentflow.shell.session_manager import SessionManager
from agentflow.shell.state_machine import States
from agentflow.shell.countdown import countdown

@pytest.fixture(autouse=True)
def mock_cwd(tmp_path):
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        yield

class FakePTY:
    def __init__(self):
        self._on_output = self._on_exit = None
        self.inputs: list[str] = []
        self._exited = False
    def write_input(self, text: str) -> None:
        self.inputs.append(text)
    def read_output(self, timeout: float = 1.0) -> bytes:
        return b""

class FakeTokenizer:
    def __init__(self, fixed_return: int | None = None):
        self._total = 0
        self._fixed = fixed_return
    def count_tokens(self, text: str, provider: str = "claude") -> int:
        return self._fixed if self._fixed is not None else 1
    def accumulate(self, text: str, provider: str = "claude") -> int:
        if self._fixed is not None:
            return self._fixed
        self._total += 1
        return self._total
    def reset(self) -> None:
        self._total = 0

def make_manager(config=None, tokenizer=None):
    pty = FakePTY()
    tok = tokenizer or FakeTokenizer()
    return SessionManager(pty, tok, config or {}), pty, tok


def fire_output(sm: SessionManager, pty: FakePTY, text: str) -> None:
    if pty._on_output:
        pty._on_output(text.encode())

def test_session_types():
    sm, pty, _ = make_manager()
    fire_output(sm, pty, "/oracle\r\n")
    assert sm.session_type == "oracle"
    sm2, pty2, _ = make_manager()
    fire_output(sm2, pty2, "/orchestrate\r\n")
    assert sm2.session_type == "orchestrator"

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

def test_countdown_behavior(capsys):
    callback = MagicMock()
    with patch("agentflow.shell.countdown.time") as mock_time:
        mock_time.sleep = MagicMock()
        countdown(3, on_complete=callback)
    callback.assert_called_once()
    assert "Restarting" in capsys.readouterr().err
    callback.reset_mock()
    with patch("agentflow.shell.countdown.time") as mock_time:
        mock_time.sleep = MagicMock(side_effect=KeyboardInterrupt)
        countdown(3, on_complete=callback)
    callback.assert_not_called()

def test_turn_output_history():
    sm, pty, _ = make_manager()
    for _ in range(3):
        fire_output(sm, pty, "response")
    pre_boundary = sm._current_turn_output_tokens
    assert pre_boundary > 1
    fire_output(sm, pty, "\n\n")
    assert sm._turn_output_history == [pre_boundary]
    assert sm._current_turn_output_tokens < pre_boundary
    sm, pty, _ = make_manager()
    for _ in range(15):
        fire_output(sm, pty, "response")
        fire_output(sm, pty, "\n\n")
    assert len(sm._turn_output_history) == 10

def test_incremental_write_verbosity_log(tmp_path):
    sm, pty, _ = make_manager()
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        fire_output(sm, pty, "some response")
        fire_output(sm, pty, "\n\n")
    assert not (tmp_path / ".agentflow").exists()
    (tmp_path / ".agentflow").mkdir()
    sm2, pty2, _ = make_manager()
    sm2.session_type = "oracle"
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        fire_output(sm2, pty2, "some response")
        fire_output(sm2, pty2, "\n\n")
    log_path = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1 and json.loads(lines[0])["turn"] == 1

def test_on_session_exit_registered_on_pty():
    sm, pty, _ = make_manager()
    assert pty._on_exit == sm._on_session_exit

def test_ansi_strip():
    sm, _, _ = make_manager()
    assert sm._ansi_strip("\x1b[32mGreen text\x1b[0m") == "Green text"

def test_detect_read_path():
    sm, _, _ = make_manager()
    assert sm._detect_read_path("Read tool agentflow/config/settings.py") == "agentflow/config/settings.py"

def test_primary_triggers():
    tok = FakeTokenizer(fixed_return=85_000)
    sm, pty, _ = make_manager(config={"handoff_primary_tokens": 80_000}, tokenizer=tok)
    sm.session_type = "orchestrator"
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-001")
        mock_hf.assert_called_once()

def test_primary_suppressed_cases():
    tok = FakeTokenizer(fixed_return=85_000)
    sm, pty, _ = make_manager(config={"handoff_primary_tokens": 80_000}, tokenizer=tok)
    sm.session_type = "orchestrator"
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

def test_task_token_bracketing_logs(tmp_path):
    (tmp_path / ".agentflow").mkdir()
    (tmp_path / ".agentflow" / "current_round.json").write_text(json.dumps({
        "estimated_lines_per_task": {"T-067": 45}, "file_counts_per_task": {"T-067": 2}
    }), encoding="utf-8")
    sm, pty, tok = make_manager()
    sm.session_type = "orchestrator"
    (tmp_path / "home").mkdir()
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path), patch.object(pathlib.Path, "home", return_value=tmp_path / "home"):
        tok.accumulate("init", "claude")
        fire_output(sm, pty, "AGENTFLOW_TASK_START:T-067")
        assert sm._task_start_tokens.get("T-067") == 2
        tok.accumulate("worker work", "claude")
        tok.accumulate("more work", "claude")
        fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-067")
        log_file = tmp_path / "home" / ".agentflow" / "task_token_log.jsonl"
        assert log_file.exists()
        record = json.loads(log_file.read_text(encoding="utf-8").strip().split("\n")[0])
        assert record["task_id"] == "T-067" and record["token_delta"] == 3
        assert record["estimated_lines"] == 45 and record["file_count"] == 2

def test_session_manager_arm_reread(tmp_path):
    (tmp_path / ".agentflow").mkdir()
    arm_file = tmp_path / ".agentflow" / "verbosity_ab_arm.txt"
    arm_file.write_text("initial_arm", encoding="utf-8")
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, pty, _ = make_manager()
        assert sm._arm == "initial_arm"
        fire_output(sm, pty, "/oracle\r\n")
        fire_output(sm, pty, "response content\n\n")
        arm_file.write_text("new_arm", encoding="utf-8")
        fire_output(sm, pty, "/clear\r\n")
        fire_output(sm, pty, "/oracle\r\n")
        fire_output(sm, pty, "response content\n\n")
        assert sm._arm == "new_arm"

def test_manual_handoff_reset_on_clear(tmp_path):
    (tmp_path / ".agentflow").mkdir()
    sm, pty, _ = make_manager()
    sm._manual_handoff = True
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        fire_output(sm, pty, "/clear\n")
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

def test_pty_audit_logging(tmp_path):
    """T-151: trigger via primary path (80K + task_just_completed)."""
    (tmp_path / ".agentflow").mkdir()
    tok = FakeTokenizer(fixed_return=100)
    sm, pty, _ = make_manager(config={"handoff_primary_tokens": 80_000}, tokenizer=tok)
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm._project_root = tmp_path
        sm._task_complete_path = tmp_path / ".agentflow" / "task_complete.json"
        sm._handoff_complete_path = tmp_path / ".agentflow" / "handoff_complete.json"
        for cmd in ["/oracle\r\n", "/handoff\r\n", "/clear\n"]:
            fire_output(sm, pty, cmd)
        # Set above primary threshold and send task_complete signal
        tok._fixed, sm.session_type = 85_000, "oracle"
        with patch.object(sm, "trigger_handoff") as mock_hf:
            fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-999")
            mock_hf.assert_called_once()
        with patch("agentflow.shell.session_manager.countdown") as mock_cd:
            mock_cd.side_effect = lambda s, on_complete, **kw: on_complete()
            sm._force_async_handoff = True
            sm.trigger_handoff(trigger="manual")
            (tmp_path / ".agentflow" / "handoff_complete.json").write_text("{}", encoding="utf-8")
            sm.poll()
            sm.trigger_handoff(trigger="auto")
            sm.poll()
    log_path = tmp_path / ".agentflow" / "pty_audit.jsonl"
    assert log_path.exists()
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").strip().split("\n")]
    event_names = [e["event"] for e in events]
    for ev in ["session_type_transition", "manual_handoff_set", "clear_detected", "manual_handoff_reset", "token_evaluation", "trigger_handoff", "restart_session"]:
        assert ev in event_names

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

def test_on_enter_restarting_calls_restart_child():
    sm, pty, _ = make_manager()
    with patch.object(sm, "restart_child") as mock_restart:
        sm.on_enter_restarting()
        mock_restart.assert_called_once()
        assert sm._just_restarted is True
        assert not any("/clear" in inp for inp in pty.inputs)

def test_restart_child_resets_token_accumulator(tmp_path):
    """T-150: restart_child() must zero _last_accumulated_tokens and reset the tokenizer."""
    sm, pty, tok = make_manager()
    pty.child_pid = None  # no real process to kill

    # Simulate accumulated tokens from a previous session
    sm._last_accumulated_tokens = 95_000
    tok._total = 95_000

    with (
        patch("agentflow.shell.process_manager.spawn_new_child"),
        patch.object(sm._state_machine, "transition"),
    ):
        sm.restart_child()

    assert sm._last_accumulated_tokens == 0, "_last_accumulated_tokens must be reset to 0 after restart"
    assert tok._total == 0, "tokenizer running total must be reset to 0 after restart"


def test_idle_poll_no_longer_triggers_on_token_count(tmp_path):
    """T-151: poll() must NOT trigger handoff based on safety/ceiling token counts.
    The poll loop only responds to signal files; threshold-based triggers are
    exclusively handled in output_handler via the primary path."""
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        # 125K tokens — formerly triggered safety handoff; must stay IDLE now
        sm, pty, _ = make_manager(config={"handoff_primary_tokens": 80_000})
        sm._state_machine.state = States.IDLE
        sm._last_accumulated_tokens = 125_000
        with patch.object(sm, "trigger_handoff") as mock_hf:
            sm.poll()
            mock_hf.assert_not_called()
        assert sm._state_machine.state == States.IDLE

        # 155K tokens — formerly triggered ceiling handoff; must stay IDLE now
        sm2, pty2, _ = make_manager(config={"handoff_primary_tokens": 80_000})
        sm2._state_machine.state = States.IDLE
        sm2._last_accumulated_tokens = 155_000
        with patch.object(sm2, "trigger_handoff") as mock_hf:
            sm2.poll()
            mock_hf.assert_not_called()
        assert sm2._state_machine.state == States.IDLE


def test_init_state_with_preexisting_current_round(tmp_path):
    (tmp_path / ".agentflow").mkdir()
    (tmp_path / ".agentflow" / "current_round.json").write_text("{}", encoding="utf-8")
    pty, tok = FakePTY(), FakeTokenizer()
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm = SessionManager(pty, tok, {})
    assert sm._state_machine.state == States.TASK_RUNNING
    (tmp_path / ".agentflow" / "task_complete.json").write_text("{}", encoding="utf-8")
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm2 = SessionManager(pty, tok, {})
    assert sm2._state_machine.state == States.IDLE


# --- T-121: per-state deadlines, ANSI reset, stdin gating ---
@pytest.mark.parametrize("state,elapsed,expect_idle", [
    (States.HANDOFF_PENDING, 91, True), (States.TASK_COMPLETE, 31, True),
    (States.RESTARTING, 31, True), (States.DEAD_CHILD, 11, True),
    (States.TASK_RUNNING, 1000, False),
])
def test_deadline_fires(tmp_path, state, elapsed, expect_idle):
    sm, _, _ = make_manager()
    sm._state_machine.state = state
    sm._deadline_state = state
    sm._deadline_entered_at = 0.0
    with patch("agentflow.shell.handoff_handler.time") as mt:
        mt.monotonic.return_value = elapsed
        with patch("os.kill"), patch("os.waitpid", return_value=(0, 0)):
            sm.poll()
    assert sm._state_machine.state == (States.IDLE if expect_idle else state)

def test_handoff_complete_via_poll_not_loop(tmp_path):
    sm, _, _ = make_manager()
    sm._state_machine.state = States.HANDOFF_PENDING
    sm._handoff_complete_path = tmp_path / ".agentflow" / "handoff_complete.json"
    sm._handoff_complete_path.parent.mkdir(parents=True, exist_ok=True)
    sm._handoff_complete_path.write_text("{}", encoding="utf-8")
    with patch.object(sm, "restart_child"): sm.poll()
    assert sm._state_machine.state == States.RESTARTING

def test_on_enter_restarting_emits_ansi_reset():
    sm, _, _ = make_manager()
    written = []
    with patch("os.write", side_effect=lambda fd, b: written.append((fd, b))):
        with patch.object(sm, "restart_child"): sm.on_enter_restarting()
    assert (1, b"\x1b[0m") in written

def test_stdin_gating_condition():
    sm, _, _ = make_manager()
    sm._state_machine.state = States.RESTARTING
    assert (sm._state_machine.state != States.RESTARTING) is False
    sm._state_machine.state = States.IDLE
    assert (sm._state_machine.state != States.RESTARTING) is True


# ---------------------------------------------------------------------------
# T-148: PTY stdin submission — injected commands must use \r not \n
# ---------------------------------------------------------------------------

def test_t148_handoff_injection_uses_cr(tmp_path):
    """T-148: handle_enter_handoff_pending writes /handoff\\r (CR) not LF.

    PTY line discipline submits on CR (0x0D); LF leaves the command buffered.
    """
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

    # Must end with \r (0x0D), NOT \n (0x0A)
    handoff_inputs = [s for s in pty.inputs if "/handoff" in s]
    assert handoff_inputs, "No /handoff command was written"
    assert all(s.endswith("\r") for s in handoff_inputs), (
        f"Expected /handoff to end with \\r, got: {handoff_inputs!r}"
    )
    assert not any(s.endswith("\n") for s in handoff_inputs), (
        f"Unexpected LF in /handoff injection: {handoff_inputs!r}"
    )


def test_t148_restart_injection_uses_cr(tmp_path):
    """T-148: on_enter_idle writes /oracle\\r (CR) not LF when just_restarted.

    The just_restarted flag triggers command injection in on_enter_idle;
    that injection must use CR so the PTY line discipline submits it immediately.
    """
    sm, pty, _ = make_manager()
    sm.session_type = "oracle"
    sm._just_restarted = True

    # Trigger the injection path directly (on_enter_idle owns the injection)
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm.on_enter_idle()

    oracle_inputs = [s for s in pty.inputs if "/oracle" in s]
    assert oracle_inputs, "No /oracle command was injected after restart"
    assert all(s.endswith("\r") for s in oracle_inputs), (
        f"Expected /oracle to end with \\r (CR), got: {oracle_inputs!r}"
    )


def test_t148_restart_injection_orchestrate_uses_cr(tmp_path):
    """T-148: orchestrator session injects /orchestrate\\r (CR) after restart."""
    sm, pty, _ = make_manager()
    sm.session_type = "orchestrator"
    sm._just_restarted = True

    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm.on_enter_idle()

    orchestrate_inputs = [s for s in pty.inputs if "/orchestrate" in s]
    assert orchestrate_inputs, "No /orchestrate command was injected after restart"
    assert all(s.endswith("\r") for s in orchestrate_inputs), (
        f"Expected /orchestrate to end with \\r (CR), got: {orchestrate_inputs!r}"
    )


def test_t148_no_lf_in_pty_injections(tmp_path):
    """T-148: no write_input call from handoff/restart paths may end with bare LF.

    Regression guard: if any injection uses \\n instead of \\r, PTY command
    submission silently stalls and the session hangs.
    """
    sm, pty, _ = make_manager()
    sm.session_type = "oracle"
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

    # Filter to command-injection inputs only (not user pass-through)
    slash_inputs = [s for s in pty.inputs if s.startswith("/") and s.strip("/") in
                    ("handoff\r", "oracle\r", "orchestrate\r", "handoff\n", "oracle\n", "orchestrate\n")]
    bare_lf = [s for s in slash_inputs if s.endswith("\n") and not s.endswith("\r\n")]
    assert bare_lf == [], (
        f"T-148 regression: these injections use bare LF instead of CR: {bare_lf!r}"
    )


# ---------------------------------------------------------------------------
# T-149: stale handoff_complete.json is cleared before poll loop
# ---------------------------------------------------------------------------

def test_t149_stale_handoff_complete_cleared_on_enter(tmp_path, monkeypatch):
    """T-149: handle_enter_handoff_pending deletes a pre-existing handoff_complete.json.

    A stale file from a previous session must be removed *before* write_input
    is called so the poll loop cannot instantly see it and trigger a restart storm.
    """
    from agentflow.shell.handoff_handler import handle_enter_handoff_pending

    # Place a stale file where the handler will look
    monkeypatch.chdir(tmp_path)
    stale_dir = tmp_path / ".agentflow"
    stale_dir.mkdir(parents=True, exist_ok=True)
    stale_file = stale_dir / "handoff_complete.json"
    stale_file.write_text("{}", encoding="utf-8")
    assert stale_file.exists(), "pre-condition: stale file must exist"

    # Build a minimal manager stub
    sm, pty, _ = make_manager()
    sm._current_trigger = "auto"
    sm._last_accumulated_tokens = 0

    # Track deletion order vs write_input order
    deleted_before_write = []

    original_write = pty.write_input

    def tracking_write(text):
        # At the moment write_input is called, the stale file must already be gone
        deleted_before_write.append(not stale_file.exists())
        original_write(text)

    pty.write_input = tracking_write

    handle_enter_handoff_pending(sm)

    assert not stale_file.exists(), "stale handoff_complete.json must be deleted by handle_enter_handoff_pending"
    assert deleted_before_write, "write_input must have been called"
    assert all(deleted_before_write), "stale file must be deleted BEFORE write_input is called"


def test_t149_no_stale_file_is_noop(tmp_path, monkeypatch):
    """T-149: handle_enter_handoff_pending is a no-op when no stale file exists."""
    from agentflow.shell.handoff_handler import handle_enter_handoff_pending

    monkeypatch.chdir(tmp_path)
    stale_file = tmp_path / ".agentflow" / "handoff_complete.json"
    assert not stale_file.exists(), "pre-condition: no stale file"

    sm, pty, _ = make_manager()
    sm._current_trigger = "auto"
    sm._last_accumulated_tokens = 0

    # Should not raise; write_input should still be called normally
    handle_enter_handoff_pending(sm)

    assert not stale_file.exists()
    assert any("/handoff" in s for s in pty.inputs), "write_input('/handoff\\r') must still be called"
