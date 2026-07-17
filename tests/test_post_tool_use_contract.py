"""Tests for audit_orchestrator_direct_write in agentflow/hooks/post_tool_use.py"""
from __future__ import annotations
import json
import os
from pathlib import Path

import pytest


def _make_session(agentflow_dir: Path, sid: str, session_type: str) -> None:
    sess_dir = agentflow_dir / "sessions" / sid
    sess_dir.mkdir(parents=True, exist_ok=True)
    (sess_dir / "session_state.json").write_text(json.dumps({"session_type": session_type}))


def _get_violations(agentflow_dir: Path) -> list[dict]:
    log = agentflow_dir / "hook_drain_debug.jsonl"
    if not log.exists():
        return []
    return [
        json.loads(line)
        for line in log.read_text().splitlines()
        if line.strip() and json.loads(line).get("event") == "contract_violation"
    ]


def test_audit_write_feature_file_no_round_json(tmp_path, monkeypatch):
    """Write to feature file, current_round.json absent, session=orchestrator → violation."""
    from agentflow.hooks.post_tool_use import audit_orchestrator_direct_write
    af = tmp_path / ".agentflow"
    af.mkdir()
    sid = "test-sid-001"
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", sid)
    _make_session(af, sid, "orchestrator")

    audit_orchestrator_direct_write("Write", {"file_path": str(tmp_path / "src/main.py")}, af)

    violations = _get_violations(af)
    assert len(violations) == 1
    assert violations[0]["rule"] == "orchestrator_direct_write"
    assert violations[0]["tool"] == "Write"


def test_audit_write_feature_file_round_json_exists(tmp_path, monkeypatch):
    """Write to feature file when current_round.json exists → no violation."""
    from agentflow.hooks.post_tool_use import audit_orchestrator_direct_write
    af = tmp_path / ".agentflow"
    af.mkdir()
    sid = "test-sid-002"
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", sid)
    _make_session(af, sid, "orchestrator")
    (af / "current_round.json").write_text(json.dumps({"round_id": "r1", "task_ids": ["T-100"]}))

    audit_orchestrator_direct_write("Write", {"file_path": str(tmp_path / "src/main.py")}, af)

    assert _get_violations(af) == []


def test_audit_write_state_file(tmp_path, monkeypatch):
    """Write to .agentflow/ state file → no violation regardless."""
    from agentflow.hooks.post_tool_use import audit_orchestrator_direct_write
    af = tmp_path / ".agentflow"
    af.mkdir()
    sid = "test-sid-003"
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", sid)
    _make_session(af, sid, "orchestrator")

    audit_orchestrator_direct_write("Write", {"file_path": str(af / "state.json")}, af)

    assert _get_violations(af) == []


def test_audit_edit_orchestrate_md_no_round_json(tmp_path, monkeypatch):
    """Edit to execution_plan.md → no violation (state file)."""
    from agentflow.hooks.post_tool_use import audit_orchestrator_direct_write
    af = tmp_path / ".agentflow"
    af.mkdir()
    sid = "test-sid-004"
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", sid)
    _make_session(af, sid, "orchestrator")

    audit_orchestrator_direct_write("Edit", {"file_path": str(tmp_path / "execution_plan.md")}, af)

    assert _get_violations(af) == []


def test_audit_session_type_oracle(tmp_path, monkeypatch):
    """Write to feature file, session_type=oracle → no violation."""
    from agentflow.hooks.post_tool_use import audit_orchestrator_direct_write
    af = tmp_path / ".agentflow"
    af.mkdir()
    sid = "test-sid-005"
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", sid)
    _make_session(af, sid, "oracle")

    audit_orchestrator_direct_write("Write", {"file_path": str(tmp_path / "src/main.py")}, af)

    assert _get_violations(af) == []


def test_audit_no_sid_env(tmp_path, monkeypatch):
    """SID absent from env → no violation (silent skip)."""
    from agentflow.hooks.post_tool_use import audit_orchestrator_direct_write
    af = tmp_path / ".agentflow"
    af.mkdir()
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)

    audit_orchestrator_direct_write("Write", {"file_path": str(tmp_path / "src/main.py")}, af)

    assert _get_violations(af) == []


def test_audit_bash_tool(tmp_path, monkeypatch):
    """tool_name=Bash → no violation."""
    from agentflow.hooks.post_tool_use import audit_orchestrator_direct_write
    af = tmp_path / ".agentflow"
    af.mkdir()
    sid = "test-sid-007"
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", sid)
    _make_session(af, sid, "orchestrator")

    audit_orchestrator_direct_write("Bash", {"command": "echo hello"}, af)

    assert _get_violations(af) == []
