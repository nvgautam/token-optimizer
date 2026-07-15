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
