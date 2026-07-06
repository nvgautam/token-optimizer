"""Tests for agentflow.shell.session_manager and agentflow.shell.countdown."""
from __future__ import annotations
import json
import pathlib
import time
from unittest.mock import MagicMock, patch
from agentflow.shell.session_manager import SessionManager
from agentflow.shell.countdown import countdown

class FakePTY:
    def __init__(self):
        self._on_output = None
        self._on_exit = None
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
        # Intercept write_input to write handoff complete file synchronously in test
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
            
    assert "/handoff\n" in pty.inputs
    assert "/clear\n" in pty.inputs
    assert pty.inputs.index("/handoff\n") < pty.inputs.index("/clear\n")

def test_safety_and_ceiling_triggers():
    tok = FakeTokenizer(fixed_return=121_000)
    sm, pty, _ = make_manager(config={"handoff_safety_tokens": 120_000, "handoff_hard_ceiling_tokens": 150_000}, tokenizer=tok)
    sm.session_type = "oracle"
    sm._auto_reset_enabled = True
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "some output chunk")
        mock_hf.assert_called_once()
    
    # Suppressed when task in flight
    sm, pty, _ = make_manager(config={"handoff_safety_tokens": 120_000, "handoff_hard_ceiling_tokens": 150_000}, tokenizer=tok)
    sm.session_type = "oracle"
    sm._auto_reset_enabled = True
    sm._task_start_tokens["T-001"] = 50_000
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "some output chunk")
        mock_hf.assert_not_called()

    # Ceiling fires anyway
    tok._fixed = 151_000
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "some output chunk")
        mock_hf.assert_called_once()

    # Manual handoff suppresses auto
    tok._fixed = 121_000
    sm._task_start_tokens.clear()
    sm._manual_handoff = True
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "some output chunk")
        mock_hf.assert_not_called()

def test_countdown_behavior(capsys):
    callback = MagicMock()
    with patch("agentflow.shell.countdown.time") as mock_time:
        mock_time.sleep = MagicMock()
        countdown(3, on_complete=callback)
    callback.assert_called_once()
    assert "Restarting" in capsys.readouterr().err
    
    # Keyboard Interrupt
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

    # Max 10 boundary tracking
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

    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    sm2, pty2, _ = make_manager()
    sm2.session_type = "oracle"
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        fire_output(sm2, pty2, "some response")
        fire_output(sm2, pty2, "\n\n")
    log_path = agentflow_dir / "verbosity_log.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    assert json.loads(lines[0])["turn"] == 1

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
    sm._auto_reset_enabled = True
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-001")
        mock_hf.assert_called_once()

def test_primary_suppressed_cases():
    tok = FakeTokenizer(fixed_return=85_000)
    sm, pty, _ = make_manager(config={"handoff_primary_tokens": 80_000, "handoff_safety_tokens": 200_000, "handoff_hard_ceiling_tokens": 300_000}, tokenizer=tok)
    sm.session_type = "orchestrator"
    sm._task_start_tokens["T-002"] = 40_000
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-001")
        mock_hf.assert_not_called()
    tok._fixed = 50_000
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-001")
        mock_hf.assert_not_called()
    tok._fixed = 85_000
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "some regular output")
        mock_hf.assert_not_called()

def test_task_token_bracketing_logs(tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    (agentflow_dir / "current_round.json").write_text(json.dumps({
        "estimated_lines_per_task": {"T-067": 45}, "file_counts_per_task": {"T-067": 2}
    }), encoding="utf-8")
    sm, pty, tok = make_manager()
    sm.session_type = "orchestrator"
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path), patch.object(pathlib.Path, "home", return_value=home_dir):
        tok.accumulate("init", "claude")
        fire_output(sm, pty, "AGENTFLOW_TASK_START:T-067")
        assert sm._task_start_tokens.get("T-067") == 2
        tok.accumulate("worker work", "claude")
        tok.accumulate("more work", "claude")
        fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-067")
        log_file = home_dir / ".agentflow" / "task_token_log.jsonl"
        assert log_file.exists()
        record = json.loads(log_file.read_text(encoding="utf-8").strip().split("\n")[0])
        assert record["task_id"] == "T-067"
        assert record["token_delta"] == 3
        assert record["estimated_lines"] == 45
        assert record["file_count"] == 2

def test_session_manager_arm_reread(tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    arm_file = agentflow_dir / "verbosity_ab_arm.txt"
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
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    sm, pty, _ = make_manager()
    sm._manual_handoff = True
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        fire_output(sm, pty, "/clear\n")
    assert sm._manual_handoff is False

def test_tokenizer_resets_on_clear_prevents_rehangoff(tmp_path):
    class PreloadedTokenizer(FakeTokenizer):
        def __init__(self, seed: int):
            super().__init__()
            self._total = seed
        def accumulate(self, text, provider="claude"):
            self._total += 1
            return self._total
        def reset(self):
            self._total = 0

    tok = PreloadedTokenizer(seed=130_000)
    sm, pty, _ = make_manager(config={"handoff_safety_tokens": 120_000}, tokenizer=tok)
    sm.session_type = "oracle"
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        with patch.object(sm, "trigger_handoff") as mock_hf:
            fire_output(sm, pty, "/clear\n")
            fire_output(sm, pty, "Welcome back")
            mock_hf.assert_not_called()

def test_tokenizer_resets_on_spawn_prevents_ceiling_loop(tmp_path):
    """Regression: tokenizer must reset when child restarts, not just on /clear.

    Bug: on_enter_restarting() kills the old child before /clear is processed, so
    the /clear detection in _handle_output never fires.  The new child inherits the
    old accumulated count and immediately re-triggers the ceiling threshold, causing
    the handoff skill output to repeat indefinitely ("numbers repeated").
    """
    class SeededTokenizer(FakeTokenizer):
        def __init__(self, seed: int):
            super().__init__()
            self._total = seed
        def accumulate(self, text, provider="claude"):
            self._total += 1
            return self._total

    tok = SeededTokenizer(seed=150_000)
    sm, pty, _ = make_manager(config={"handoff_hard_ceiling_tokens": 150_000}, tokenizer=tok)

    # _spawn_new_child skips PTY fork when _command is absent (FakePTY has none)
    sm._spawn_new_child()

    assert sm._last_accumulated_tokens == 0
    assert tok._total == 0

    # Subsequent output must NOT immediately re-trigger ceiling
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm._project_root = tmp_path
        with patch.object(sm, "trigger_handoff") as mock_hf:
            fire_output(sm, pty, "Orchestrating new round")
            mock_hf.assert_not_called()


def test_pty_audit_logging(tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    tok = FakeTokenizer(fixed_return=100)
    sm, pty, _ = make_manager(config={"handoff_hard_ceiling_tokens": 1000}, tokenizer=tok)
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm._project_root = tmp_path
        sm._task_complete_path = tmp_path / ".agentflow" / "task_complete.json"
        sm._handoff_complete_path = tmp_path / ".agentflow" / "handoff_complete.json"

        fire_output(sm, pty, "/oracle\n")
        fire_output(sm, pty, "/handoff\n")
        fire_output(sm, pty, "/clear\n")
        tok._fixed = 2000
        sm.session_type = "oracle"
        sm._auto_reset_enabled = True
        with patch.object(sm, "trigger_handoff") as mock_hf:
            fire_output(sm, pty, "some text")
            mock_hf.assert_called_once()
        
        with patch("agentflow.shell.session_manager.countdown") as mock_cd:
            mock_cd.side_effect = lambda s, on_complete, **kw: on_complete()
            # Force async so it doesn't trigger synchronous pytest fallback
            sm._force_async_handoff = True
            sm.trigger_handoff(trigger="manual")
            
            # Simulate the write of handoff complete file to transition HANDOFF_PENDING -> RESTARTING -> IDLE
            sm._handoff_complete_path.parent.mkdir(parents=True, exist_ok=True)
            sm._handoff_complete_path.write_text("{}", encoding="utf-8")
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
            duration = time.monotonic() - t0
            assert duration < 0.5
            assert sm._handoff_in_progress is True
            
            # Simulate handoff complete file being written
            sm._handoff_complete_path.parent.mkdir(parents=True, exist_ok=True)
            sm._handoff_complete_path.write_text("{}", encoding="utf-8")
            sm.poll()
            
    assert sm._handoff_in_progress is False
    assert "/handoff\n" in pty.inputs
    assert "/clear\n" in pty.inputs

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

def test_on_enter_idle_reinjects_skill():
    sm, pty, _ = make_manager()
    # Simulate a restart that sets just_restarted flag
    sm._just_restarted = True
    sm.session_type = "oracle"
    sm.on_enter_idle()
    assert "/oracle\n" in pty.inputs

    sm._just_restarted = True
    sm.session_type = "orchestrator"
    sm.on_enter_idle()
    assert "/orchestrate\n" in pty.inputs

    sm._just_restarted = True
    sm.session_type = "unknown"
    sm.on_enter_idle()
    # No command should be written for unknown session type
    assert not any(cmd.startswith("/unknown") for cmd in pty.inputs)

def test_restart_end_to_end_via_state_machine(tmp_path):
    # Tokenizer that will exceed hard ceiling to trigger handoff
    tok = FakeTokenizer(fixed_return=151_000)
    sm, pty, _ = make_manager(config={"handoff_hard_ceiling_tokens": 150_000}, tokenizer=tok)
    sm.session_type = "oracle"
    sm._auto_reset_enabled = True
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm._project_root = tmp_path
        sm._handoff_complete_path = tmp_path / ".agentflow" / "handoff_complete.json"
        # Patch countdown to return immediately
        with patch("agentflow.shell.session_manager.countdown") as mock_cd:
            mock_cd.side_effect = lambda s, on_complete, **kw: on_complete()
            # Fire output that exceeds ceiling and triggers handoff synchronously
            fire_output(sm, pty, "big output chunk")
            # At this point handoff should be in progress
            assert sm._handoff_in_progress is True
            # Simulate handoff completion file
            sm._handoff_complete_path.parent.mkdir(parents=True, exist_ok=True)
            sm._handoff_complete_path.write_text("{}", encoding="utf-8")
            sm.poll()
            # After poll the state machine should have completed restart
            assert sm._handoff_in_progress is False
            # Tokenizer should have been reset and accumulated tokens cleared
            assert sm._last_accumulated_tokens == 0
            assert getattr(tok, "_total", None) == 0

def test_on_enter_restarting_oserror_safe(tmp_path):
    sm, pty, _ = make_manager()
    # Make write_input raise OSError
    def failing_write_input(text):
        raise OSError("closed")
    pty.write_input = failing_write_input
    # Patch restart_child to track call
    with patch.object(sm, "restart_child") as mock_restart:
        sm.on_enter_restarting()
        mock_restart.assert_called_once()
        # Ensure no exception propagates and _just_restarted flag is set
        assert sm._just_restarted is True

