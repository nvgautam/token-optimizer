"""Tests for check_drain_restart — TASK_RUNNING support + tif.exists() gate."""
from __future__ import annotations
import json
import time
from pathlib import Path
import pytest

from agentflow.shell.state_machine import StateMachine, States
import os


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
        self.trigger_handoff_calls: list[str] = []

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

    def trigger_handoff(self, trigger: str = "auto") -> None:
        self.trigger_handoff_calls.append(trigger)

    def __getattr__(self, name: str):
        # Return 0.0 for _skip_last_* cooldown sentinels
        if name.startswith("_skip_last_"):
            return 0.0
        raise AttributeError(name)


def _make_manager(tmp_path: Path, state: States, fill_tokens: int = 90000):
    mgr = _StubManager(tmp_path, state, fill_tokens)
    return mgr, tmp_path / ".agentflow"


def _audit_tags(mgr: _StubManager) -> set[str]:
    """Collect all event names and skip reasons from audit calls."""
    tags: set[str] = set()
    for entry in mgr._audit_calls:
        if "event" in entry:
            tags.add(entry["event"])
        if "reason" in entry:
            tags.add(entry["reason"])
    return tags


def test_drain_fires_from_task_running_when_tif_drained(tmp_path):
    mgr, af = _make_manager(tmp_path, States.TASK_RUNNING)
    (af / "tasks_in_flight.json").write_text("[]")

    from agentflow.shell.handoff_handler import check_drain_restart
    check_drain_restart(mgr)

    assert "drain_restart_triggered" in _audit_tags(mgr)


def test_drain_fires_from_idle_when_tif_drained(tmp_path):
    mgr, af = _make_manager(tmp_path, States.IDLE)
    (af / "tasks_in_flight.json").write_text("[]")

    from agentflow.shell.handoff_handler import check_drain_restart
    check_drain_restart(mgr)

    assert "drain_restart_triggered" in _audit_tags(mgr)


def test_drain_skipped_when_tif_absent(tmp_path):
    mgr, af = _make_manager(tmp_path, States.TASK_RUNNING)
    # tasks_in_flight.json deliberately not written

    from agentflow.shell.handoff_handler import check_drain_restart
    check_drain_restart(mgr)

    events = _audit_tags(mgr)
    assert "no_tasks_in_flight_file" in events
    assert "drain_restart_triggered" not in events


def test_drain_skipped_when_tif_nonempty(tmp_path):
    mgr, af = _make_manager(tmp_path, States.TASK_RUNNING)
    (af / "tasks_in_flight.json").write_text('["T-001"]')

    from agentflow.shell.handoff_handler import check_drain_restart
    check_drain_restart(mgr)

    events = _audit_tags(mgr)
    assert "tasks_in_flight_nonempty" in events
    assert "drain_restart_triggered" not in events


def test_drain_skipped_from_handoff_pending(tmp_path):
    mgr, af = _make_manager(tmp_path, States.HANDOFF_PENDING)
    (af / "tasks_in_flight.json").write_text("[]")

    from agentflow.shell.handoff_handler import check_drain_restart
    check_drain_restart(mgr)

    events = _audit_tags(mgr)
    assert "state_not_idle" in events


def test_drain_skipped_when_fill_below_threshold(tmp_path):
    mgr, af = _make_manager(tmp_path, States.TASK_RUNNING, fill_tokens=50000)
    (af / "tasks_in_flight.json").write_text("[]")

    from agentflow.shell.handoff_handler import check_drain_restart
    check_drain_restart(mgr)

    events = _audit_tags(mgr)
    assert "fill_tokens_below_threshold" in events


def test_write_merged_and_clear_deletes_current_round(tmp_path):
    """_write_merged_and_clear deletes current_round.json after merge."""
    mgr, af = _make_manager(tmp_path, States.TASK_RUNNING)

    # Ensure current_round.json exists
    current_round_path = af / "current_round.json"
    assert current_round_path.exists()

    from agentflow.shell.drain_restart import _write_merged_and_clear
    _write_merged_and_clear(mgr)

    # Verify current_round.json was deleted
    assert not current_round_path.exists(), "current_round.json should be deleted after _write_merged_and_clear"


def test_write_merged_and_clear_idempotent_when_current_round_absent(tmp_path):
    """_write_merged_and_clear is idempotent when current_round.json is absent."""
    mgr, af = _make_manager(tmp_path, States.TASK_RUNNING)

    # Delete current_round.json
    current_round_path = af / "current_round.json"
    current_round_path.unlink()
    assert not current_round_path.exists()

    from agentflow.shell.drain_restart import _write_merged_and_clear
    # Should not raise an error
    _write_merged_and_clear(mgr)

    # Verify it still doesn't exist
    assert not current_round_path.exists()
