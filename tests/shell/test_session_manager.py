"""Core tests for agentflow.shell.session_manager and agentflow.shell.countdown."""
from __future__ import annotations
import json
import os
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
    # Turn boundary is triggered by AGENTFLOW_TASK_COMPLETE, not double-newline
    sm, pty, _ = make_manager()
    for _ in range(3):
        fire_output(sm, pty, "response")
    pre_boundary = sm._current_turn_output_tokens
    assert pre_boundary > 1
    # Double-newline should NOT trigger a boundary (old heuristic removed)
    fire_output(sm, pty, "\n\n")
    assert sm._turn_output_history == []
    assert sm._current_turn_output_tokens >= pre_boundary
    # AGENTFLOW_TASK_COMPLETE triggers the boundary
    sm2, pty2, _ = make_manager()
    for _ in range(3):
        fire_output(sm2, pty2, "response")
    pre2 = sm2._current_turn_output_tokens
    fire_output(sm2, pty2, "AGENTFLOW_TASK_COMPLETE:T-001\n")
    assert len(sm2._turn_output_history) == 1
    assert sm2._turn_output_history[0] >= pre2
    assert sm2._current_turn_output_tokens == 0
    # History trimmed to 10 items
    sm3, pty3, _ = make_manager()
    for i in range(15):
        fire_output(sm3, pty3, "response")
        fire_output(sm3, pty3, f"AGENTFLOW_TASK_COMPLETE:T-{i:03d}\n")
    assert len(sm3._turn_output_history) == 10


def test_incremental_write_verbosity_log(tmp_path):
    # Turn boundary (and verbosity log write) is triggered by AGENTFLOW_TASK_COMPLETE signal
    # Without .agentflow dir, no log is written
    sm, pty, _ = make_manager()
    fire_output(sm, pty, "some response")
    fire_output(sm, pty, "AGENTFLOW_TASK_COMPLETE:T-001\n")
    assert not (tmp_path / ".agentflow" / "verbosity_log.jsonl").exists()
    # With .agentflow dir, log is written on task complete
    (tmp_path / ".agentflow").mkdir(exist_ok=True)
    sm2, pty2, _ = make_manager()
    sm2.session_type = "oracle"
    fire_output(sm2, pty2, "some response")
    fire_output(sm2, pty2, "AGENTFLOW_TASK_COMPLETE:T-001\n")
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
    (tmp_path / ".agentflow" / "session_state.json").write_text(
        json.dumps({"session_type": "orchestrator"}), encoding="utf-8"
    )
    pty, tok = FakePTY(), FakeTokenizer()
    # Run without SID so _task_complete_path uses the flat path
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path), \
         patch.dict(os.environ, {}, clear=False) as env:
        env.pop("AGENTFLOW_SESSION_ID", None)
        sm = SessionManager(pty, tok, {})
    assert sm._state_machine.state == States.TASK_RUNNING
    (tmp_path / ".agentflow" / "task_complete.json").write_text("{}", encoding="utf-8")
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path), \
         patch.dict(os.environ, {}, clear=False) as env:
        env.pop("AGENTFLOW_SESSION_ID", None)
        sm2 = SessionManager(pty, tok, {})
    assert sm2._state_machine.state == States.IDLE


def test_init_task_running_gated_on_orchestrator_session_type(tmp_path):
    """T-194: Oracle sessions stay IDLE when current_round.json exists; orchestrator enters TASK_RUNNING."""
    (tmp_path / ".agentflow").mkdir()
    (tmp_path / ".agentflow" / "current_round.json").write_text("{}", encoding="utf-8")
    pty, tok = FakePTY(), FakeTokenizer()

    # Test 1: Oracle session with current_round.json should stay in IDLE
    (tmp_path / ".agentflow" / "session_state.json").write_text(
        json.dumps({"session_type": "oracle"}), encoding="utf-8"
    )
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm_oracle = SessionManager(pty, tok, {})
    assert sm_oracle.session_type == "oracle"
    assert sm_oracle._state_machine.state == States.IDLE

    # Test 2: Orchestrator session with current_round.json should enter TASK_RUNNING
    (tmp_path / ".agentflow" / "session_state.json").write_text(
        json.dumps({"session_type": "orchestrator"}), encoding="utf-8"
    )
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm_orch = SessionManager(pty, tok, {})
    assert sm_orch.session_type == "orchestrator"
    assert sm_orch._state_machine.state == States.TASK_RUNNING


def _test_spawn_new_child_command(just_restarted, session_type, expected_args):
    """Helper: verify spawn_new_child command."""
    from agentflow.shell.process_manager import spawn_new_child
    import pty as pty_module

    sm, pty, _ = make_manager()
    sm._just_restarted = just_restarted
    sm.session_type = session_type

    exec_called = []
    with patch.object(pty_module, "fork", return_value=(0, 123)), \
         patch("os.execvp", side_effect=lambda cmd, args: exec_called.append(args) or (_ for _ in ()).throw(SystemExit(127))), \
         patch("os._exit"):
        try:
            spawn_new_child(sm)
        except SystemExit:
            pass

    assert len(exec_called) == 1
    assert exec_called[0] == expected_args, f"Expected {expected_args}, got {exec_called[0]}"


def test_spawn_new_child_appends_skill():
    """T-195: spawn_new_child appends /{skill} when _just_restarted and session_type set."""
    _test_spawn_new_child_command(True, "orchestrator", ["claude", "/orchestrate"])
    _test_spawn_new_child_command(True, "oracle", ["claude", "/oracle"])


def test_spawn_new_child_no_skill_conditions():
    """T-195: spawn_new_child omits skill when _just_restarted=False, session_type=None, or unknown type."""
    _test_spawn_new_child_command(False, "orchestrator", ["claude"])
    _test_spawn_new_child_command(True, None, ["claude"])
    _test_spawn_new_child_command(True, "reviewer", ["claude"])  # unknown type → no skill


def test_on_enter_idle_clears_just_restarted_no_injection():
    """T-195: on_enter_idle clears _just_restarted without writing to pty.inputs."""
    sm, pty, _ = make_manager()
    sm._just_restarted = True
    sm.session_type = "orchestrator"
    sm.on_enter_idle()
    assert sm._just_restarted is False
    assert len(pty.inputs) == 0  # No injection — skill is now passed via spawn arg


def test_sync_session_type_reads_sid_keyed_file_first():
    """When both sid-keyed and unkeyed session_state files exist, read sid-keyed file."""
    sm, pty, _ = make_manager()
    proj_root = sm._project_root
    agentflow_dir = proj_root / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    # Both files exist with different session types
    (agentflow_dir / "session_state_abc.json").write_text(
        json.dumps({"session_type": "oracle"}), encoding="utf-8"
    )
    (agentflow_dir / "session_state.json").write_text(
        json.dumps({"session_type": "orchestrator"}), encoding="utf-8"
    )

    # With AGENTFLOW_SESSION_ID=abc, should read oracle from sid-keyed file
    with patch.dict(os.environ, {"AGENTFLOW_SESSION_ID": "abc"}):
        sm.session_type = None  # Reset to trigger _sync_session_type
        sm._sync_session_type()
        assert sm.session_type == "oracle"


def test_sync_session_type_falls_back_to_unkeyed_when_no_sid_file():
    """When no sid-keyed file, fall back to unkeyed session_state.json."""
    sm, pty, _ = make_manager()
    proj_root = sm._project_root
    agentflow_dir = proj_root / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    # Only unkeyed file exists
    (agentflow_dir / "session_state.json").write_text(
        json.dumps({"session_type": "orchestrator"}), encoding="utf-8"
    )

    # No sid-keyed file, should read orchestrator from unkeyed file
    with patch.dict(os.environ, {"AGENTFLOW_SESSION_ID": "missing_sid"}):
        sm.session_type = None
        sm._sync_session_type()
        assert sm.session_type == "orchestrator"


def test_isolation_two_sessions_independent_state():
    """Two sessions with different sids maintain independent session_type state."""
    sm1, pty1, _ = make_manager()
    sm2, pty2, _ = make_manager()
    # Both use same project root due to mock_cwd fixture

    proj_root = sm1._project_root
    agentflow_dir = proj_root / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    # Session 1 writes oracle to session_state_s1.json
    (agentflow_dir / "session_state_s1.json").write_text(
        json.dumps({"session_type": "oracle"}), encoding="utf-8"
    )
    # Session 2 writes orchestrator to session_state_s2.json
    (agentflow_dir / "session_state_s2.json").write_text(
        json.dumps({"session_type": "orchestrator"}), encoding="utf-8"
    )

    # Session 1 with sid=s1 should read oracle
    with patch.dict(os.environ, {"AGENTFLOW_SESSION_ID": "s1"}):
        sm1.session_type = None
        sm1._sync_session_type()
        assert sm1.session_type == "oracle"

    # Session 2 with sid=s2 should read orchestrator
    with patch.dict(os.environ, {"AGENTFLOW_SESSION_ID": "s2"}):
        sm2.session_type = None
        sm2._sync_session_type()
        assert sm2.session_type == "orchestrator"

def test_task_complete_path_uses_sid_from_env():
    """When AGENTFLOW_SESSION_ID=abc env var set, _task_complete_path returns sessions/abc/task_complete.json."""
    sm, pty, _ = make_manager()
    proj_root = sm._project_root

    # With SID set, should return sessions/<sid>/task_complete.json
    sid = "test-abc-123"
    with patch.dict(os.environ, {"AGENTFLOW_SESSION_ID": sid}):
        path = sm._task_complete_path
        expected = proj_root / ".agentflow" / "sessions" / sid / "task_complete.json"
        assert path == expected

def test_task_complete_path_uses_flat_path_without_sid():
    """Without SID env, _task_complete_path returns flat .agentflow/task_complete.json."""
    sm, pty, _ = make_manager()
    proj_root = sm._project_root

    # Without SID, should return flat .agentflow/task_complete.json
    with patch.dict(os.environ, {"AGENTFLOW_SESSION_ID": ""}):
        path = sm._task_complete_path
        expected = proj_root / ".agentflow" / "task_complete.json"
        assert path == expected
