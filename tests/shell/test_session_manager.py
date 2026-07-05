"""Tests for agentflow.shell.session_manager and agentflow.shell.countdown."""
from __future__ import annotations
import json
import pathlib
from unittest.mock import MagicMock, patch
from agentflow.shell.session_manager import SessionManager
from agentflow.shell.countdown import countdown

class FakePTY:
    def __init__(self):
        self._on_output = None
        self._on_exit = None
        self.inputs: list[str] = []
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

def test_session_type_oracle():
    sm, pty, _ = make_manager()
    fire_output(sm, pty, "/oracle\r\n")
    assert sm.session_type == "oracle"

def test_session_type_orchestrate():
    sm, pty, _ = make_manager()
    fire_output(sm, pty, "/orchestrate\r\n")
    assert sm.session_type == "orchestrator"

def test_trigger_handoff_writes_commands():
    sm, pty, _ = make_manager()
    pty.read_output = lambda timeout=1.0: b"HANDOFF_COMPLETE\n"
    with patch("agentflow.shell.session_manager.countdown") as mock_cd:
        mock_cd.side_effect = lambda s, on_complete, **kw: on_complete()
        sm.trigger_handoff()
    assert "/handoff\n" in pty.inputs
    assert "/clear\n" in pty.inputs
    assert pty.inputs.index("/handoff\n") < pty.inputs.index("/clear\n")

def test_safety_net_fires_no_task_in_flight():
    tok = FakeTokenizer(fixed_return=121_000)
    sm, pty, _ = make_manager(config={"handoff_safety_tokens": 120_000}, tokenizer=tok)
    sm.session_type = "oracle"
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "some output chunk")
        mock_hf.assert_called_once()

def test_safety_net_suppressed_when_task_in_flight():
    tok = FakeTokenizer(fixed_return=121_000)
    sm, pty, _ = make_manager(config={"handoff_safety_tokens": 120_000, "handoff_hard_ceiling_tokens": 200_000}, tokenizer=tok)
    sm.session_type = "oracle"
    sm._task_start_tokens["T-001"] = 50_000
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "some output chunk")
        mock_hf.assert_not_called()

def test_hard_ceiling_fires_even_with_task_in_flight():
    tok = FakeTokenizer(fixed_return=151_000)
    sm, pty, _ = make_manager(config={"handoff_hard_ceiling_tokens": 150_000}, tokenizer=tok)
    sm.session_type = "oracle"
    sm._task_start_tokens["T-001"] = 50_000
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "some output chunk")
        mock_hf.assert_called_once()

def test_manual_handoff_suppresses_auto():
    tok = FakeTokenizer(fixed_return=121_000)
    sm, pty, _ = make_manager(config={"handoff_safety_tokens": 120_000}, tokenizer=tok)
    sm.session_type = "oracle"
    sm._manual_handoff = True
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "some output chunk")
        mock_hf.assert_not_called()

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
    assert "Restarting" in err and "3s" in err

def test_countdown_keyboard_interrupt():
    callback = MagicMock()
    call_count = [0]
    def raising_sleep(n: float) -> None:
        call_count[0] += 1
        if call_count[0] == 1:
            raise KeyboardInterrupt
    with patch("agentflow.shell.countdown.time") as mock_time:
        mock_time.sleep = raising_sleep
        countdown(3, on_complete=callback)
    callback.assert_not_called()

def test_output_tokens_reset_at_turn_boundary():
    sm, pty, _ = make_manager()
    for _ in range(3):
        fire_output(sm, pty, "some response content")
    pre_boundary = sm._current_turn_output_tokens
    assert pre_boundary > 1
    fire_output(sm, pty, "\n\n")
    assert sm._turn_output_history == [pre_boundary]
    assert sm._current_turn_output_tokens < pre_boundary

def test_turn_output_history_appended_at_boundary():
    sm, pty, _ = make_manager()
    for _ in range(3):
        fire_output(sm, pty, "response")
        fire_output(sm, pty, "\n\n")
    assert len(sm._turn_output_history) == 3

def test_turn_output_history_max_10():
    sm, pty, _ = make_manager()
    for _ in range(15):
        fire_output(sm, pty, "response")
        fire_output(sm, pty, "\n\n")
    assert len(sm._turn_output_history) == 10

def test_incremental_write_verbosity_log(tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    sm, pty, _ = make_manager()
    sm.session_type = "oracle"
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        fire_output(sm, pty, "some response")
        fire_output(sm, pty, "\n\n")
    log_path = agentflow_dir / "verbosity_log.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["turn"] == 1
    assert record["session_type"] == "oracle"
    assert record["output_tokens"] > 0

def test_incremental_write_skips_when_no_agentflow_dir(tmp_path):
    sm, pty, _ = make_manager()
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        fire_output(sm, pty, "some response")
        fire_output(sm, pty, "\n\n")
    assert not (tmp_path / ".agentflow").exists()

def test_on_session_exit_registered_on_pty():
    sm, pty, _ = make_manager()
    assert pty._on_exit == sm._on_session_exit

def test_ansi_strip():
    sm, _, _ = make_manager()
    assert sm._ansi_strip("\x1b[32mGreen text\x1b[0m and \x1b[1mBold\x1b[0m") == "Green text and Bold"
    assert sm._ansi_strip("Read tool agentflow/config/settings.py") == "Read tool agentflow/config/settings.py"

def test_detect_read_path():
    sm, _, _ = make_manager()
    assert sm._detect_read_path("Read tool agentflow/config/settings.py for configuration") == "agentflow/config/settings.py"
    assert sm._detect_read_path('Read(file_path="/Users/gautam/code/token-optimizer/design_status.md")') == "/Users/gautam/code/token-optimizer/design_status.md"
    assert sm._detect_read_path('Read("/Users/gautam/code/token-optimizer/design_status.md")') == "/Users/gautam/code/token-optimizer/design_status.md"
    assert sm._detect_read_path("no read call here at all") is None
    assert sm._detect_read_path("read the config.py file for details") is None

def test_primary_fires_on_task_complete_above_threshold():
    tok = FakeTokenizer(fixed_return=85_000)
    sm, pty, _ = make_manager(config={"handoff_primary_tokens": 80_000}, tokenizer=tok)
    sm.session_type = "orchestrator"
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-001")
        mock_hf.assert_called_once()

def test_primary_suppressed_when_task_still_in_flight():
    tok = FakeTokenizer(fixed_return=85_000)
    sm, pty, _ = make_manager(config={"handoff_primary_tokens": 80_000, "handoff_safety_tokens": 200_000, "handoff_hard_ceiling_tokens": 300_000}, tokenizer=tok)
    sm.session_type = "orchestrator"
    sm._task_start_tokens["T-002"] = 40_000  # second task still running
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-001")
        mock_hf.assert_not_called()

def test_primary_suppressed_when_below_threshold():
    tok = FakeTokenizer(fixed_return=50_000)
    sm, pty, _ = make_manager(config={"handoff_primary_tokens": 80_000, "handoff_safety_tokens": 200_000, "handoff_hard_ceiling_tokens": 300_000}, tokenizer=tok)
    sm.session_type = "orchestrator"
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-001")
        mock_hf.assert_not_called()

def test_primary_suppressed_when_no_task_complete_signal():
    tok = FakeTokenizer(fixed_return=85_000)
    sm, pty, _ = make_manager(config={"handoff_primary_tokens": 80_000, "handoff_safety_tokens": 200_000, "handoff_hard_ceiling_tokens": 300_000}, tokenizer=tok)
    sm.session_type = "orchestrator"
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "some regular output above 80K")
        mock_hf.assert_not_called()

def test_task_token_bracketing_logs(tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    round_file = agentflow_dir / "current_round.json"
    round_file.write_text(json.dumps({
        "estimated_lines_per_task": {"T-067": 45},
        "file_counts_per_task": {"T-067": 2}
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
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["task_id"] == "T-067"
        assert record["session_type"] == "orchestrator"
        assert record["token_delta"] == 3
        assert record["estimated_lines"] == 45
        assert record["file_count"] == 2
        assert "timestamp" in record
        assert "T-067" not in sm._task_start_tokens

def test_session_manager_arm_reread(tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    arm_file = agentflow_dir / "verbosity_ab_arm.txt"
    
    # 1. Write initial arm value
    arm_file.write_text("initial_arm", encoding="utf-8")
    
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, pty, _ = make_manager()
        assert sm._arm == "initial_arm"
        
        # Simulating first session start
        fire_output(sm, pty, "/oracle\r\n")
        assert sm.session_type == "oracle"
        
        # Simulating some outputs
        fire_output(sm, pty, "response content")
        fire_output(sm, pty, "\n\n")
        assert sm._turn_count == 1
        
        # 2. Write new arm value (simulating deployment/restart/coin-flip)
        arm_file.write_text("new_arm", encoding="utf-8")
        
        # Simulating a /clear and restart session
        fire_output(sm, pty, "/clear\r\n")
        assert sm.session_type is None
        assert sm._turn_count == 0
        
        # Simulating next session start
        fire_output(sm, pty, "/oracle\r\n")
        assert sm.session_type == "oracle"
        
        # Simulating first turn boundary of next session
        fire_output(sm, pty, "response content")
        fire_output(sm, pty, "\n\n")
        assert sm._turn_count == 1
        
        # The arm should now have been re-read and updated to new_arm!
        assert sm._arm == "new_arm"


def test_manual_handoff_reset_on_clear(tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    sm, pty, _ = make_manager()
    sm._manual_handoff = True
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        fire_output(sm, pty, "/clear\n")
    assert sm._manual_handoff is False


def test_pty_audit_logging(tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    tok = FakeTokenizer(fixed_return=100)
    sm, pty, _ = make_manager(config={"handoff_hard_ceiling_tokens": 1000}, tokenizer=tok)
    
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        # 1. Transition session type
        fire_output(sm, pty, "/oracle\n")
        
        # 2. Manual handoff set
        fire_output(sm, pty, "/handoff\n")
        
        # 3. Clear / reset
        fire_output(sm, pty, "/clear\n")
        
        # 4. Trigger auto handoff
        tok._fixed = 2000
        sm.session_type = "oracle"
        
        # Mock trigger_handoff for the auto-trigger check in _handle_output
        with patch.object(sm, "trigger_handoff") as mock_hf:
            fire_output(sm, pty, "some text")
            mock_hf.assert_called_once()
            
        # 5. Call trigger_handoff directly to test its logging and restart
        pty.read_output = lambda timeout=1.0: b"HANDOFF_COMPLETE\n"
        with patch("agentflow.shell.session_manager.countdown") as mock_cd:
            mock_cd.side_effect = lambda s, on_complete, **kw: on_complete()
            sm.trigger_handoff(trigger="manual")
            sm.trigger_handoff(trigger="auto")
            
    log_path = tmp_path / ".agentflow" / "pty_audit.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    events = [json.loads(line) for line in lines]
    
    event_names = [e["event"] for e in events]
    assert "session_type_transition" in event_names
    assert "manual_handoff_set" in event_names
    assert "clear_detected" in event_names
    assert "manual_handoff_reset" in event_names
    assert "token_evaluation" in event_names
    assert "trigger_handoff" in event_names
    assert "restart_session" in event_names
