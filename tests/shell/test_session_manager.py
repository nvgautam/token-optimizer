"""Core tests for agentflow.shell.session_manager and agentflow.shell.countdown."""
from __future__ import annotations
import json
import pathlib
import sys
from unittest.mock import MagicMock, patch
import pytest
from agentflow.shell.session_manager import SessionManager
from agentflow.shell.state_machine import States
from agentflow.shell.countdown import countdown

# Make conftest importable
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from conftest import make_manager, fire_output, FakePTY, FakeTokenizer

def test_session_types():
    sm, pty, _ = make_manager()
    fire_output(sm, pty, "/oracle\r\n")
    assert sm.session_type == "oracle"
    sm2, pty2, _ = make_manager()
    fire_output(sm2, pty2, "/orchestrate\r\n")
    assert sm2.session_type == "orchestrator"


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
