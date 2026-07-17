"""T-251: SQLite round tracking + drain MERGED write tests."""
from __future__ import annotations
import json
import os
import pathlib
import sqlite3
import tempfile
import types
from unittest.mock import MagicMock, patch

import pytest

from agentflow.tools.task_db import TaskDB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path: pathlib.Path) -> TaskDB:
    return TaskDB(tmp_path / "tasks.db")


def _make_manager(tmp_path: pathlib.Path, fill_tokens: int = 90000):
    """Build a minimal mock manager that satisfies check_drain_restart."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    # session files
    sid = "test-sid-123"
    os.environ["AGENTFLOW_SESSION_ID"] = sid

    # current_round.json
    current_round = agentflow_dir / "current_round.json"
    current_round.write_text(json.dumps({
        "round_id": "R-1",
        "task_ids": ["T-100", "T-101"],
        "session_id": sid,
    }), encoding="utf-8")

    # tasks_in_flight.json — empty → drained
    tif = agentflow_dir / "tasks_in_flight.json"
    tif.write_text("{}", encoding="utf-8")

    # context_fill.json — session_file puts it at agentflow_dir/sessions/<sid>/context_fill.json
    sessions_dir = agentflow_dir / "sessions" / sid
    sessions_dir.mkdir(parents=True, exist_ok=True)
    cf = sessions_dir / "context_fill.json"
    cf.write_text(json.dumps({"fill_tokens": fill_tokens, "ts": __import__("time").time()}), encoding="utf-8")

    # execution_plan.md with addendum sections
    ep = tmp_path / "execution_plan.md"
    ep.write_text(
        "# Execution Plan\n\n"
        "| round_id | tasks | status |\n"
        "|---|---|---|\n"
        "| R-1 | T-100, T-101 | in-progress |\n\n"
        "## Addendum: T-100\n"
        "Some task content.\n\n"
        "## Addendum: T-101\n"
        "Another task.\n",
        encoding="utf-8",
    )

    audit_events: list[dict] = []

    from agentflow.shell.state_machine import States

    sm = MagicMock()
    sm.state = States.IDLE

    manager = MagicMock()
    manager.session_type = "orchestrator"
    manager._project_root = tmp_path
    manager._state_machine = sm
    manager._current_round_path = current_round
    manager._tasks_in_flight_path = tif
    manager._handoff_in_progress = False
    manager._last_restart_ts = 0.0
    manager._last_accumulated_tokens = fill_tokens
    manager._config = {"handoff_primary_tokens": 80000}
    manager._auto_handoff_disabled = MagicMock(return_value=False)
    # Configure MagicMock to return 0.0 for any _skip_last_* attribute access
    for key in ["_skip_last_handoff_in_progress_or_disabled", "_skip_last_no_current_round", "_skip_last_no_tasks_in_flight_file"]:
        setattr(manager, key, 0.0)

    def _log_audit(event: dict) -> None:
        audit_events.append(event)

    manager._log_audit = _log_audit
    manager._audit_events = audit_events

    return manager, audit_events, ep, agentflow_dir, sid


# ---------------------------------------------------------------------------
# check_drain_restart integration tests
# ---------------------------------------------------------------------------

def _run_drain(manager):
    from agentflow.shell.handoff_handler import check_drain_restart
    check_drain_restart(manager)


class TestDrainMergedWrite:
    def test_drain_writes_merged_to_execution_plan_addendum(self, tmp_path):
        manager, audit_events, ep, agentflow_dir, sid = _make_manager(tmp_path)
        _run_drain(manager)

        content = ep.read_text(encoding="utf-8")
        assert "## Addendum: T-100 (MERGED)" in content
        assert "## Addendum: T-101 (MERGED)" in content

    def test_drain_writes_merged_idempotent(self, tmp_path):
        manager, audit_events, ep, agentflow_dir, sid = _make_manager(tmp_path)
        _run_drain(manager)
        # First drain deletes TIF; recreate so second drain can fire
        manager._tasks_in_flight_path.write_text("[]", encoding="utf-8")
        _run_drain(manager)  # second run

        content = ep.read_text(encoding="utf-8")
        # Must NOT appear twice
        assert content.count("## Addendum: T-100 (MERGED)") == 1
        assert content.count("## Addendum: T-101 (MERGED)") == 1

    def test_drain_merged_write_failure_does_not_block_restart(self, tmp_path):
        manager, audit_events, ep, agentflow_dir, sid = _make_manager(tmp_path)
        # Remove execution_plan.md so the write fails
        ep.unlink()

        _run_drain(manager)

        # restart_session must still have been called
        manager._state_machine.transition.assert_called_with("restart_session")

    def test_drain_clears_active_round_after_merge(self, tmp_path):
        manager, audit_events, ep, agentflow_dir, sid = _make_manager(tmp_path)

        # Pre-populate the db via raw SQL so we can verify clear
        db_path = tmp_path / ".agentflow" / "tasks.db"
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS rounds (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute("INSERT OR REPLACE INTO rounds (key, value) VALUES ('active_round', ?)",
                         (json.dumps({"round_id": "R-1", "task_ids": ["T-100", "T-101"]}),))
            conn.commit()

        # Verify setup
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute("SELECT value FROM rounds WHERE key = 'active_round'").fetchone()
            assert row is not None

        _run_drain(manager)

        # After drain, active round should be cleared
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute("SELECT value FROM rounds WHERE key = 'active_round'").fetchone()
            assert row is None

    def test_drain_logs_drain_merged_written_event(self, tmp_path):
        manager, audit_events, ep, agentflow_dir, sid = _make_manager(tmp_path)
        _run_drain(manager)

        events = [e["event"] for e in audit_events]
        assert "drain_merged_written" in events

        merged_event = next(e for e in audit_events if e["event"] == "drain_merged_written")
        assert merged_event["round_id"] == "R-1"
        assert "T-100" in merged_event["task_ids"]
        assert "T-101" in merged_event["task_ids"]

    def test_drain_restart_transition_fires(self, tmp_path):
        manager, audit_events, ep, agentflow_dir, sid = _make_manager(tmp_path)
        _run_drain(manager)

        manager._state_machine.transition.assert_called_with("restart_session")
