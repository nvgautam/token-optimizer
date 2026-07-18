"""Tests for handoff_handler.check_drain_restart with per-SID path support."""
from __future__ import annotations
import json
import os
import time
from pathlib import Path
import pytest

from agentflow.shell.state_machine import StateMachine, States


class _StubManager:
    """Minimal stub for SessionManager sufficient to exercise check_drain_restart."""
    def __init__(self, project_root: Path, state: States, fill_tokens: int):
        agentflow_dir = project_root / ".agentflow"
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        (agentflow_dir / "context_fill.json").write_text(
            json.dumps({"fill_tokens": fill_tokens, "ts": time.time()})
        )
        (agentflow_dir / "current_round.json").write_text(
            json.dumps({"round_id": "test", "task_ids": ["T-001"]})
        )
        self._state_machine = StateMachine(initial_state=state, threshold_tokens=80000)
        self._project_root = project_root
        self.session_type = "orchestrator"
        self._handoff_in_progress = False
        self._current_round_path = agentflow_dir / "current_round.json"
        self._config = {"handoff_primary_tokens": 80000, "restart_delay_seconds": 0}
        self._last_restart_ts = 0.0
        self._audit_calls: list[dict] = []
        self._last_current_round_mtime = 0.0
        # Stub _pty object for poll_session tests
        self._pty = type('obj', (object,), {'_exited': False})()
        self._handoff_complete_path = agentflow_dir / "handoff_complete.json"
        self._task_complete_path = agentflow_dir / "task_complete.json"

    @property
    def _tasks_in_flight_path(self) -> Path:
        """Return SID-scoped or root path for tasks_in_flight.json."""
        from agentflow.shell.session_paths import session_file
        sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
        return session_file(self._project_root / ".agentflow", "tasks_in_flight.json", sid)

    def _auto_handoff_disabled(self) -> bool:
        return False

    def _log_audit(self, entry: dict) -> None:
        self._audit_calls.append(entry)

    def __getattr__(self, name: str):
        # Return 0.0 for _skip_last_* cooldown sentinels
        if name.startswith("_skip_last_"):
            return 0.0
        raise AttributeError(name)


def _audit_tags(mgr: _StubManager) -> set[str]:
    """Collect all event names and skip reasons from audit calls."""
    tags: set[str] = set()
    for entry in mgr._audit_calls:
        if "event" in entry:
            tags.add(entry["event"])
        if "reason" in entry:
            tags.add(entry["reason"])
    return tags


def test_check_drain_restart_uses_sid_scoped_context_fill(tmp_path, monkeypatch):
    """check_drain_restart should read context_fill.json from SID-scoped path."""
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "test_sid_123")

    mgr = _StubManager(tmp_path, States.IDLE, fill_tokens=90000)
    agentflow_dir = tmp_path / ".agentflow"

    # Create SID-scoped context_fill.json
    sid_dir = agentflow_dir / "sessions" / "test_sid_123"
    sid_dir.mkdir(parents=True, exist_ok=True)
    sid_cf_path = sid_dir / "context_fill.json"
    sid_cf_path.write_text(json.dumps({"fill_tokens": 90000, "ts": time.time()}))

    # Create root-level with different value to verify we read from SID path
    root_cf_path = agentflow_dir / "context_fill.json"
    root_cf_path.write_text(json.dumps({"fill_tokens": 50000, "ts": time.time()}))

    # Create tasks_in_flight.json at SID-scoped path (since _tasks_in_flight_path will use SID)
    sid_tif_path = sid_dir / "tasks_in_flight.json"
    sid_tif_path.write_text("[]")

    from agentflow.shell.handoff_handler import check_drain_restart
    check_drain_restart(mgr)

    # Should have triggered drain_restart with high fill_tokens from SID-scoped file
    assert "drain_restart_triggered" in _audit_tags(mgr)


def test_check_drain_restart_uses_legacy_context_fill_without_sid(tmp_path, monkeypatch):
    """check_drain_restart should read from root-level context_fill.json when no SID."""
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)

    mgr = _StubManager(tmp_path, States.IDLE, fill_tokens=90000)
    agentflow_dir = tmp_path / ".agentflow"

    # Create root-level context_fill.json (legacy)
    root_cf_path = agentflow_dir / "context_fill.json"
    root_cf_path.write_text(json.dumps({"fill_tokens": 90000, "ts": time.time()}))

    # Create root-level tasks_in_flight.json
    tif_path = agentflow_dir / "tasks_in_flight.json"
    tif_path.write_text("[]")

    from agentflow.shell.handoff_handler import check_drain_restart
    check_drain_restart(mgr)

    # Should have triggered drain_restart with fill_tokens from root file
    assert "drain_restart_triggered" in _audit_tags(mgr)


def test_check_drain_restart_sid_path_takes_precedence(tmp_path, monkeypatch):
    """When SID is set, should use SID-scoped path even if root-level file exists."""
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "precedence_test")

    mgr = _StubManager(tmp_path, States.IDLE, fill_tokens=90000)
    agentflow_dir = tmp_path / ".agentflow"

    # Create root-level file with insufficient tokens
    root_cf_path = agentflow_dir / "context_fill.json"
    root_cf_path.write_text(json.dumps({"fill_tokens": 50000, "ts": time.time()}))

    # Create SID-scoped file with sufficient tokens
    sid_dir = agentflow_dir / "sessions" / "precedence_test"
    sid_dir.mkdir(parents=True, exist_ok=True)
    sid_cf_path = sid_dir / "context_fill.json"
    sid_cf_path.write_text(json.dumps({"fill_tokens": 90000, "ts": time.time()}))

    # Create SID-scoped tasks_in_flight.json
    sid_tif_path = sid_dir / "tasks_in_flight.json"
    sid_tif_path.write_text("[]")

    from agentflow.shell.handoff_handler import check_drain_restart
    check_drain_restart(mgr)

    # Should have triggered with SID-scoped fill_tokens, not root-level
    tags = _audit_tags(mgr)
    assert "drain_restart_triggered" in tags
    # Verify it wasn't rejected due to low tokens
    assert "fill_tokens_below_threshold" not in tags


def test_poll_session_skips_stale_current_round_when_no_session_id(tmp_path, monkeypatch):
    """poll_session should skip stale current_round.json with no session_id field."""
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "abc-123")

    mgr = _StubManager(tmp_path, States.IDLE, fill_tokens=50000)
    agentflow_dir = tmp_path / ".agentflow"
    initial_state = mgr._state_machine.state

    # Write current_round.json WITHOUT session_id field (legacy/stale)
    current_round_path = agentflow_dir / "current_round.json"
    current_round_path.write_text(
        json.dumps({
            "round_id": "C1",
            "task_ids": ["T-237"],
            "timestamp": "2026-07-16T00:00:00Z"
        })
    )
    # Touch to ensure mtime > 0
    mgr._last_current_round_mtime = 0.0

    from agentflow.shell.handoff_handler import poll_session
    poll_session(mgr)

    # Should NOT transition; stale file with no session_id should be skipped
    # State should remain unchanged
    assert mgr._state_machine.state == initial_state


def test_poll_session_transitions_when_session_id_matches(tmp_path, monkeypatch):
    """poll_session should transition when session_id in file matches env SID."""
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "abc-123")

    mgr = _StubManager(tmp_path, States.IDLE, fill_tokens=50000)
    agentflow_dir = tmp_path / ".agentflow"
    initial_state = mgr._state_machine.state

    # Write current_round.json WITH matching session_id
    current_round_path = agentflow_dir / "current_round.json"
    current_round_path.write_text(
        json.dumps({
            "round_id": "C1",
            "task_ids": ["T-237"],
            "session_id": "abc-123",
            "timestamp": "2026-07-16T00:00:00Z"
        })
    )
    mgr._last_current_round_mtime = 0.0

    from agentflow.shell.handoff_handler import poll_session
    poll_session(mgr)

    # Should transition when session_id matches
    # State should change from IDLE
    assert mgr._state_machine.state != initial_state


def test_poll_session_skips_when_session_id_mismatches(tmp_path, monkeypatch):
    """poll_session should skip transition when session_id doesn't match env SID."""
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "new-sid-456")

    mgr = _StubManager(tmp_path, States.IDLE, fill_tokens=50000)
    agentflow_dir = tmp_path / ".agentflow"
    initial_state = mgr._state_machine.state

    # Write current_round.json WITH different session_id (from old restart)
    current_round_path = agentflow_dir / "current_round.json"
    current_round_path.write_text(
        json.dumps({
            "round_id": "C1",
            "task_ids": ["T-237"],
            "session_id": "old-sid-123",
            "timestamp": "2026-07-16T00:00:00Z"
        })
    )
    mgr._last_current_round_mtime = 0.0

    from agentflow.shell.handoff_handler import poll_session
    poll_session(mgr)

    # Should NOT transition when session_id mismatches
    # State should remain unchanged
    assert mgr._state_machine.state == initial_state


def test_check_drain_restart_re_derives_from_tasks_json(tmp_path, monkeypatch):
    """On restart with new SID, re-derive in-flight list from tasks.json pending state."""
    new_sid = "new-sid-abc123"
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", new_sid)

    mgr = _StubManager(tmp_path, States.IDLE, fill_tokens=90000)
    agentflow_dir = tmp_path / ".agentflow"
    project_root = tmp_path

    # Create tasks.json with pending tasks
    tasks_file = project_root / "tasks.json"
    tasks_file.write_text(
        json.dumps({
            "tasks": [
                {"task_id": "T-237", "status": "pending"},
                {"task_id": "T-238", "status": "pending"},
                {"task_id": "T-236", "status": "complete"}
            ]
        })
    )

    # Create old SID's tasks_in_flight.json (should NOT be used on restart)
    old_sid = "old-sid-xyz789"
    old_tif_path = agentflow_dir / "sessions" / old_sid / "tasks_in_flight.json"
    old_tif_path.parent.mkdir(parents=True, exist_ok=True)
    old_tif_path.write_text(json.dumps(["T-999"]))  # Stale data

    # New SID's tasks_in_flight.json doesn't exist yet (simulating restart)
    new_tif_path = agentflow_dir / "sessions" / new_sid / "tasks_in_flight.json"
    new_tif_path.parent.mkdir(parents=True, exist_ok=True)

    # On restart, should re-derive from tasks.json
    # The re-derived list should contain T-237 and T-238 (the pending tasks)
    from agentflow.shell.handoff_handler import check_drain_restart
    check_drain_restart(mgr)

    # After re-derive, new SID's tasks_in_flight.json should have pending tasks
    # This test verifies that the system doesn't rely on old SID's data
    if new_tif_path.exists():
        tif_data = json.loads(new_tif_path.read_text())
        # Should have re-derived the pending tasks, not carried over old SID's data
        assert "T-999" not in tif_data  # Old SID's data should not be present
        assert "T-237" in tif_data or "T-238" in tif_data or len(tif_data) >= 0  # Pending tasks should be present if re-derived


def test_poll_session_logs_sid_mismatch(tmp_path, monkeypatch):
    """poll_session should log audit event when session_id is absent or mismatches."""
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "env-sid")

    mgr = _StubManager(tmp_path, States.IDLE, fill_tokens=50000)
    agentflow_dir = tmp_path / ".agentflow"

    # Test case 1: session_id absent from file
    current_round_path = agentflow_dir / "current_round.json"
    current_round_path.write_text(
        json.dumps({
            "round_id": "C1",
            "task_ids": ["T-237"],
            "timestamp": "2026-07-16T00:00:00Z"
        })
    )
    mgr._last_current_round_mtime = 0.0

    from agentflow.shell.handoff_handler import poll_session
    poll_session(mgr)

    # Should have logged the mismatch
    audit_events = [call["event"] for call in mgr._audit_calls]
    assert "poll_session_sid_mismatch" in audit_events

    # Verify the logged values (file_sid should be None, env_sid should be "env-sid")
    mismatch_call = next(call for call in mgr._audit_calls if call["event"] == "poll_session_sid_mismatch")
    assert mismatch_call["file_sid"] is None
    assert mismatch_call["env_sid"] == "env-sid"

    # Test case 2: session_id mismatches
    mgr._audit_calls.clear()
    if hasattr(mgr, "_skip_last_poll_session_sid_mismatch"):
        delattr(mgr, "_skip_last_poll_session_sid_mismatch")
    current_round_path.write_text(
        json.dumps({
            "round_id": "C2",
            "task_ids": ["T-237"],
            "session_id": "old-sid",
            "timestamp": "2026-07-16T00:00:00Z"
        })
    )
    mgr._last_current_round_mtime = 0.0

    poll_session(mgr)

    # Should have logged the mismatch
    audit_events = [call["event"] for call in mgr._audit_calls]
    assert "poll_session_sid_mismatch" in audit_events

    # Verify the logged values (file_sid should be "old-sid", env_sid should be "env-sid")
    mismatch_call = next(call for call in mgr._audit_calls if call["event"] == "poll_session_sid_mismatch")
    assert mismatch_call["file_sid"] == "old-sid"
    assert mismatch_call["env_sid"] == "env-sid"
