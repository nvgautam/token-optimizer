"""Integration test: CLI round start → drain → restart path end-to-end.

Exercises the complete flow introduced by T-260:
  1. cmd_round_start atomically writes current_round.json + tasks_in_flight.json
  2. check_drain_restart respects non-empty tif (no false restart)
  3. Draining tif to [] triggers restart detection
  4. After restart trigger, state is cleaned up (no stale current_round.json)
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agentflow.cli_db import cmd_round_start
from agentflow.shell.session_paths import session_file
from agentflow.shell.state_machine import StateMachine, States


# ---------------------------------------------------------------------------
# Shared stub (same pattern as tests/test_handoff_drain_restart.py)
# ---------------------------------------------------------------------------

class _StubManager:
    """Minimal SessionManager stub sufficient to exercise check_drain_restart."""

    def __init__(self, project_root: Path, fill_tokens: int = 90000) -> None:
        agentflow_dir = project_root / ".agentflow"
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        (agentflow_dir / "context_fill.json").write_text(
            json.dumps({"fill_tokens": fill_tokens, "ts": time.time()})
        )
        self._state_machine = StateMachine(initial_state=States.TASK_RUNNING, threshold_tokens=80000)
        self._project_root = project_root
        self.session_type = "orchestrator"
        self._handoff_in_progress = False
        self._current_round_path = agentflow_dir / "current_round.json"
        self._config = {"handoff_primary_tokens": 80000, "restart_delay_seconds": 0}
        self._last_restart_ts = 0.0
        self._audit_calls: list[dict] = []

    @property
    def _tasks_in_flight_path(self) -> Path:
        sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
        return session_file(self._project_root / ".agentflow", "tasks_in_flight.json", sid)

    def _auto_handoff_disabled(self) -> bool:
        return False

    def _log_audit(self, entry: dict) -> None:
        self._audit_calls.append(entry)

    def trigger_handoff(self, trigger: str = "auto") -> None:
        pass

    def __getattr__(self, name: str):
        if name.startswith("_skip_last_"):
            return 0.0
        raise AttributeError(name)


def _audit_events(mgr: _StubManager) -> set[str]:
    return {e["event"] for e in mgr._audit_calls if "event" in e}


def _audit_skip_reasons(mgr: _StubManager) -> set[str]:
    return {e["reason"] for e in mgr._audit_calls if "reason" in e}


def _make_round_args(
    task_ids: list[str],
    round_id: str = "test-round",
    sid: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(task_ids=task_ids, round_id=round_id, sid=sid)


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin CWD to tmp_path and clear session ID env var for test isolation."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)


# ---------------------------------------------------------------------------
# Step 1+2: CLI writes both files atomically and consistently
# ---------------------------------------------------------------------------

class TestRoundStartFileWrites:
    def test_current_round_json_written(self, tmp_path: Path) -> None:
        rc = cmd_round_start(_make_round_args(["T-001", "T-002"]))
        assert rc == 0
        data = json.loads((tmp_path / ".agentflow" / "current_round.json").read_text())
        assert data["round_id"] == "test-round"
        assert data["task_ids"] == ["T-001", "T-002"]
        assert data["estimated_lines_per_task"] == {}
        assert data["file_counts_per_task"] == {}

    def test_tasks_in_flight_json_written(self, tmp_path: Path) -> None:
        cmd_round_start(_make_round_args(["T-001"]))
        tif = tmp_path / ".agentflow" / "tasks_in_flight.json"
        assert tif.exists()
        assert json.loads(tif.read_text()) == ["T-001"]

    def test_both_files_task_ids_consistent(self, tmp_path: Path) -> None:
        """task_ids in current_round.json must match tasks_in_flight.json."""
        task_ids = ["T-010", "T-011", "T-012"]
        cmd_round_start(_make_round_args(task_ids))
        round_data = json.loads((tmp_path / ".agentflow" / "current_round.json").read_text())
        tif_data = json.loads((tmp_path / ".agentflow" / "tasks_in_flight.json").read_text())
        assert round_data["task_ids"] == tif_data


# ---------------------------------------------------------------------------
# Step 3: drain check skips when tasks are still in flight
# ---------------------------------------------------------------------------

class TestDrainSkipsWhenInFlight:
    def test_no_restart_triggered(self, tmp_path: Path) -> None:
        cmd_round_start(_make_round_args(["T-001"]))
        mgr = _StubManager(tmp_path)
        from agentflow.shell.handoff_handler import check_drain_restart
        check_drain_restart(mgr)
        assert "drain_restart_triggered" not in _audit_events(mgr)
        assert "tasks_in_flight_nonempty" in _audit_skip_reasons(mgr)

    def test_current_round_preserved_when_in_flight(self, tmp_path: Path) -> None:
        """current_round.json must remain intact while tasks are in flight."""
        cmd_round_start(_make_round_args(["T-001"]))
        mgr = _StubManager(tmp_path)
        from agentflow.shell.handoff_handler import check_drain_restart
        check_drain_restart(mgr)
        assert (tmp_path / ".agentflow" / "current_round.json").exists()

    def test_tif_preserved_when_in_flight(self, tmp_path: Path) -> None:
        """tasks_in_flight.json must not be removed when tasks are running."""
        cmd_round_start(_make_round_args(["T-001"]))
        mgr = _StubManager(tmp_path)
        from agentflow.shell.handoff_handler import check_drain_restart
        check_drain_restart(mgr)
        assert (tmp_path / ".agentflow" / "tasks_in_flight.json").exists()
        data = json.loads((tmp_path / ".agentflow" / "tasks_in_flight.json").read_text())
        assert data == ["T-001"]


# ---------------------------------------------------------------------------
# Step 4+5: draining tif to [] triggers restart and cleans up state
# ---------------------------------------------------------------------------

class TestDrainTriggers:
    def test_restart_triggered_when_tif_drained(self, tmp_path: Path) -> None:
        cmd_round_start(_make_round_args(["T-001"]))
        (tmp_path / ".agentflow" / "tasks_in_flight.json").write_text("[]")
        mgr = _StubManager(tmp_path)
        from agentflow.shell.handoff_handler import check_drain_restart
        check_drain_restart(mgr)
        assert "drain_restart_triggered" in _audit_events(mgr)

    def test_current_round_cleared_after_restart(self, tmp_path: Path) -> None:
        """No stale current_round.json left after restart — next round can begin."""
        cmd_round_start(_make_round_args(["T-001"]))
        (tmp_path / ".agentflow" / "tasks_in_flight.json").write_text("[]")
        mgr = _StubManager(tmp_path)
        from agentflow.shell.handoff_handler import check_drain_restart
        check_drain_restart(mgr)
        assert "drain_restart_triggered" in _audit_events(mgr)
        assert not (tmp_path / ".agentflow" / "current_round.json").exists(), (
            "current_round.json must be removed after restart to unblock the next round"
        )

    def test_tif_removed_after_restart(self, tmp_path: Path) -> None:
        """tasks_in_flight.json is unlinked as part of the restart cleanup."""
        cmd_round_start(_make_round_args(["T-001"]))
        (tmp_path / ".agentflow" / "tasks_in_flight.json").write_text("[]")
        mgr = _StubManager(tmp_path)
        from agentflow.shell.handoff_handler import check_drain_restart
        check_drain_restart(mgr)
        assert not (tmp_path / ".agentflow" / "tasks_in_flight.json").exists()


# ---------------------------------------------------------------------------
# Full end-to-end lifecycle in one test
# ---------------------------------------------------------------------------

def test_full_round_lifecycle(tmp_path: Path) -> None:
    """End-to-end: round start → in-flight check (skip) → drain → restart → cleanup."""
    from agentflow.shell.handoff_handler import check_drain_restart

    agentflow_dir = tmp_path / ".agentflow"
    round_path = agentflow_dir / "current_round.json"
    tif_path = agentflow_dir / "tasks_in_flight.json"

    # 1. Start round via CLI layer — both files written atomically
    args = _make_round_args(["T-001", "T-002"], round_id="lifecycle-round")
    assert cmd_round_start(args) == 0
    assert round_path.exists()
    assert tif_path.exists()
    assert json.loads(tif_path.read_text()) == ["T-001", "T-002"]

    # 2. First drain check: tasks still in flight → no restart
    mgr = _StubManager(tmp_path)
    check_drain_restart(mgr)
    assert "drain_restart_triggered" not in _audit_events(mgr)
    assert round_path.exists(), "current_round.json must remain while tasks in flight"

    # 3. Simulate task completion: drain tif to tombstone
    tif_path.write_text("[]")

    # 4. Second drain check: tif is empty → restart triggered
    mgr2 = _StubManager(tmp_path)
    check_drain_restart(mgr2)
    assert "drain_restart_triggered" in _audit_events(mgr2)

    # 5. Verify state is fully cleaned — no stale files blocking next round
    assert not round_path.exists(), "current_round.json must be cleared after restart"
    assert not tif_path.exists(), "tasks_in_flight.json must be cleared after restart"


# ---------------------------------------------------------------------------
# Subprocess: verify the actual agentflow CLI entry point works end-to-end
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Consolidated state: task_complete.json eliminated
# ---------------------------------------------------------------------------

class TestTaskCompleteEliminated:
    def test_task_done_no_longer_writes_task_complete(self, tmp_path: Path) -> None:
        """task_done must write [] tombstone but NOT task_complete.json."""
        from agentflow.shell.pty_signal import task_done, task_start
        task_start("T-001", workspace_root=tmp_path)
        task_done("T-001", workspace_root=tmp_path)
        assert not (tmp_path / ".agentflow" / "task_complete.json").exists()
        tif = tmp_path / ".agentflow" / "tasks_in_flight.json"
        assert tif.exists() and json.loads(tif.read_text()) == []

    def test_poll_session_transitions_task_running_on_empty_tif(self, tmp_path: Path) -> None:
        """poll_session must transition TASK_RUNNING→TASK_COMPLETE when tif==[]."""
        from agentflow.shell.handoff_handler import poll_session
        from agentflow.shell.state_machine import States
        from tests.shell.conftest import make_manager
        from unittest.mock import MagicMock
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        (agentflow_dir / "tasks_in_flight.json").write_text("[]")
        sm, _, _ = make_manager()
        sm._project_root = tmp_path
        sm.session_type = "orchestrator"
        sm._state_machine.state = States.TASK_RUNNING
        sm._log_audit = MagicMock()
        poll_session(sm)
        assert sm._state_machine.state == States.TASK_COMPLETE


# ---------------------------------------------------------------------------
# tasks.json terminal-status gate
# ---------------------------------------------------------------------------

class TestTasksJsonGate:
    def test_drain_skips_when_tasks_not_terminal(self, tmp_path: Path) -> None:
        """drain skips when current_round task is still 'pending' in tasks.json."""
        from agentflow.shell.drain_restart import check_drain_restart
        mgr = _StubManager(tmp_path, fill_tokens=90000)
        agentflow_dir = tmp_path / ".agentflow"
        (agentflow_dir / "current_round.json").write_text(
            json.dumps({"round_id": "r1", "task_ids": ["T-001"]})
        )
        (agentflow_dir / "tasks_in_flight.json").write_text("[]")
        (tmp_path / "tasks.json").write_text(
            json.dumps({"tasks": [{"task_id": "T-001", "status": "pending"}]})
        )
        check_drain_restart(mgr)
        assert "drain_restart_triggered" not in _audit_events(mgr)
        assert "tasks_not_terminal" in _audit_skip_reasons(mgr)

    def test_drain_proceeds_when_all_tasks_terminal(self, tmp_path: Path) -> None:
        """drain proceeds when all tasks are complete or skipped."""
        from agentflow.shell.drain_restart import check_drain_restart
        mgr = _StubManager(tmp_path, fill_tokens=90000)
        agentflow_dir = tmp_path / ".agentflow"
        (agentflow_dir / "current_round.json").write_text(
            json.dumps({"round_id": "r1", "task_ids": ["T-001", "T-002"]})
        )
        (agentflow_dir / "tasks_in_flight.json").write_text("[]")
        (tmp_path / "tasks.json").write_text(
            json.dumps({"tasks": [
                {"task_id": "T-001", "status": "complete"},
                {"task_id": "T-002", "status": "skipped"},
            ]})
        )
        check_drain_restart(mgr)
        assert "drain_restart_triggered" in _audit_events(mgr)


# ---------------------------------------------------------------------------
# /cost capture and parsing
# ---------------------------------------------------------------------------

class TestCostCapture:
    def test_parse_claude_cost_valid(self) -> None:
        from agentflow.shell.usage_parser import parse_claude_cost
        text = "Total cost:  $0.2467\n  Input:  5,234 tokens ($0.0157)\n  Output:  1,234 tokens ($0.0741)\n"
        result = parse_claude_cost(text)
        assert result is not None
        assert abs(result["total_cost_usd"] - 0.2467) < 1e-6

    def test_parse_claude_cost_with_ansi(self) -> None:
        from agentflow.shell.usage_parser import parse_claude_cost
        text = "\x1b[1mTotal cost:\x1b[0m  $0.0123\n"
        result = parse_claude_cost(text)
        assert result is not None
        assert abs(result["total_cost_usd"] - 0.0123) < 1e-6

    def test_parse_claude_cost_missing_field_returns_none(self) -> None:
        from agentflow.shell.usage_parser import parse_claude_cost
        assert parse_claude_cost("no cost data here") is None
        assert parse_claude_cost("") is None


def test_round_start_via_subprocess(tmp_path: Path) -> None:
    """`agentflow round start` via subprocess exits 0 and writes correct files."""
    # Force subprocess to use worktree's agentflow package (not the installed copy).
    worktree_root = str(Path(__file__).resolve().parents[1])
    env = os.environ.copy()
    env["PYTHONPATH"] = worktree_root + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    result = subprocess.run(
        [
            sys.executable, "-m", "agentflow",
            "round", "start",
            "--task-ids", "T-100", "T-101",
            "--round-id", "sub-round",
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert result.stdout.strip() == "sub-round"

    round_path = tmp_path / ".agentflow" / "current_round.json"
    tif_path = tmp_path / ".agentflow" / "tasks_in_flight.json"
    assert round_path.exists()
    assert tif_path.exists()

    data = json.loads(round_path.read_text())
    assert data["round_id"] == "sub-round"
    assert data["task_ids"] == ["T-100", "T-101"]
    assert json.loads(tif_path.read_text()) == ["T-100", "T-101"]
