"""Integration test: user_prompt_submit → sync_session_type → check_drain_restart chain.

Regression for the production bug where session 49d9f2c0 never restarted:
- user_prompt_submit.py writes sessions/<SID>/session_state.json as "orchestrator"
- sync_session_type reads it and sets manager.session_type
- check_drain_restart proceeds past the session_type guard and triggers restart

Each piece worked in isolation; the chain was never tested end-to-end.

Note: the autouse mock_cwd fixture (conftest.py) patches pathlib.Path.cwd() → tmp_path,
so manager._project_root resolves to tmp_path throughout these tests.
"""
from __future__ import annotations
import json
import time
import pathlib
from unittest.mock import patch
from agentflow.shell.state_machine import States
from agentflow.shell.threshold_sync import sync_session_type
from agentflow.shell.drain_restart import check_drain_restart
from agentflow.shell.session_paths import session_file
from tests.shell.conftest import make_manager


TEST_SID = "deadbeef-0000-0000-0000-000000000001"


def _write_session_state(agentflow_dir: pathlib.Path, session_type: str, sid: str) -> None:
    """Simulate what user_prompt_submit.py does on /orchestrate."""
    fp = session_file(agentflow_dir, "session_state.json", sid)
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(json.dumps({"session_type": session_type}), encoding="utf-8")


def _setup_restart_conditions(tmp_path: pathlib.Path, sid: str) -> dict:
    """Write the file state that should trigger a drain restart."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    tif = session_file(agentflow_dir, "tasks_in_flight.json", sid)
    tif.parent.mkdir(parents=True, exist_ok=True)
    tif.write_text("[]", encoding="utf-8")

    cr = agentflow_dir / "current_round.json"
    cr.write_text(json.dumps({"round_id": "M-F-12", "task_ids": ["T-312"]}), encoding="utf-8")

    cf = session_file(agentflow_dir, "context_fill.json", sid)
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps({"fill_tokens": 98000, "ts": time.time()}), encoding="utf-8")

    ep = tmp_path / "execution_plan.md"
    ep.write_text("| M-F-12 [PENDING] | T-312 |\n", encoding="utf-8")

    return {"agentflow_dir": agentflow_dir, "tif": tif, "cr": cr, "cf": cf}


def test_chain_restart_triggers_when_session_state_written_by_hook(tmp_path, monkeypatch):
    """Full chain: hook writes orchestrator session_type → sync reads it → restart fires."""
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", TEST_SID)

    # Create manager BEFORE writing session_state so __init__._sync_session_type finds nothing.
    # mock_cwd (autouse) patches pathlib.Path.cwd() → tmp_path so _project_root = tmp_path already.
    sm, pty, tok = make_manager()
    assert sm.session_type != "orchestrator", "session_type must be unset before hook fires"

    paths = _setup_restart_conditions(tmp_path, TEST_SID)
    agentflow_dir = paths["agentflow_dir"]

    # Simulate user_prompt_submit.py writing session_state on /orchestrate
    _write_session_state(agentflow_dir, "orchestrator", TEST_SID)

    # sync_session_type is called by the PTY on each idle tick
    sync_session_type(sm)
    assert sm.session_type == "orchestrator", (
        "sync_session_type must read sessions/<SID>/session_state.json written by hook"
    )

    restarted = []
    with patch.object(sm._state_machine, "transition", side_effect=lambda s: restarted.append(s)):
        check_drain_restart(sm)

    assert restarted == ["restart_session"], (
        "check_drain_restart must trigger restart when session_type is orchestrator, "
        "TIF is tombstoned, and fill_tokens > threshold"
    )


def test_chain_no_restart_when_session_state_never_written(tmp_path, monkeypatch):
    """Reproduces the production bug: no session_state.json → session_type stays null → silent skip."""
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", TEST_SID)

    sm, pty, tok = make_manager()
    _setup_restart_conditions(tmp_path, TEST_SID)
    # Do NOT write session_state.json — simulates hook never firing (T-315 not yet merged)

    sync_session_type(sm)
    assert sm.session_type != "orchestrator"

    restarted = []
    with patch.object(sm._state_machine, "transition", side_effect=lambda s: restarted.append(s)):
        check_drain_restart(sm)

    assert restarted == [], (
        "Without session_state.json, check_drain_restart exits silently at session_type guard — "
        "this is the production bug that caused session 49d9f2c0 to never restart"
    )


def test_chain_no_restart_when_session_state_written_to_wrong_path(tmp_path, monkeypatch):
    """session_state.json at root agentflow_dir (no SID) is ignored when AGENTFLOW_SESSION_ID is set."""
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", TEST_SID)

    sm, pty, tok = make_manager()
    paths = _setup_restart_conditions(tmp_path, TEST_SID)
    agentflow_dir = paths["agentflow_dir"]

    # Write at root level (sid="") — wrong path when SID is active
    root_ss = agentflow_dir / "session_state.json"
    root_ss.write_text(json.dumps({"session_type": "orchestrator"}), encoding="utf-8")

    sync_session_type(sm)
    assert sm.session_type != "orchestrator", (
        "Root-level session_state.json must not satisfy sync_session_type when AGENTFLOW_SESSION_ID is set"
    )
