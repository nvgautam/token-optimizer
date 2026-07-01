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

def test_threshold_fires_for_oracle():
    tok = FakeTokenizer(fixed_return=61_000)
    sm, pty, _ = make_manager(config={"oracle_threshold_tokens": 60_000}, tokenizer=tok)
    sm.session_type = "oracle"
    with patch.object(sm, "trigger_handoff") as mock_hf:
        fire_output(sm, pty, "some output chunk")
        mock_hf.assert_called_once()

def test_manual_handoff_suppresses_auto():
    tok = FakeTokenizer(fixed_return=61_000)
    sm, pty, _ = make_manager(config={"oracle_threshold_tokens": 60_000}, tokenizer=tok)
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

def test_round_complete_above_floor(tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    round_file = agentflow_dir / "current_round.json"
    round_file.write_text(json.dumps({"closed": True}), encoding="utf-8")
    tok = FakeTokenizer(fixed_return=10_000)
    sm, pty, _ = make_manager(config={"orchestrator_threshold_tokens": 30_000, "handoff_token_floor_pct": 0.30}, tokenizer=tok)
    sm.session_type = "orchestrator"
    with patch.object(sm, "trigger_handoff") as mock_hf, patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        fire_output(sm, pty, "AGENTFLOW_ROUND_COMPLETE")
        mock_hf.assert_called_once()

def test_round_complete_below_floor(tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    round_file = agentflow_dir / "current_round.json"
    round_file.write_text(json.dumps({"closed": True}), encoding="utf-8")
    tok = FakeTokenizer(fixed_return=5000)
    sm, pty, _ = make_manager(config={"orchestrator_threshold_tokens": 30_000, "handoff_token_floor_pct": 0.30}, tokenizer=tok)
    sm.session_type = "orchestrator"
    with patch.object(sm, "trigger_handoff") as mock_hf, patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        fire_output(sm, pty, "AGENTFLOW_ROUND_COMPLETE")
        mock_hf.assert_not_called()
        log_path = agentflow_dir / "verbosity_log.jsonl"
        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event"] == "round-complete-low-tokens"
        assert not round_file.exists()

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
