"""Tests for rolling archive logic in drain_restart (T-335)."""
from __future__ import annotations
import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest

from agentflow.shell.drain_restart import (
    _archive_oldest_merged_round,
    _write_merged_and_clear,
)
from agentflow.shell.state_machine import States
from tests.shell.conftest import make_manager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ROUND_HEADER = "| Round | Tasks | Status |\n|---|---|---|\n"

def _make_ep_with_rounds(rounds: list[tuple[str, bool]]) -> str:
    """Build execution_plan.md content with given rounds.

    rounds: list of (round_id, is_merged) tuples.
    """
    header = "# Execution Plan\n\n"
    table = _ROUND_HEADER
    for rid, merged in rounds:
        suffix = " — MERGED" if merged else ""
        table += f"| {rid} | T-100 | some note |{suffix}\n"
    return header + table


def _make_manager_with_ep(tmp_path: pathlib.Path, ep_content: str):
    sm, pty, tok = make_manager()
    sm._project_root = tmp_path
    sm.session_type = "orchestrator"
    sm._state_machine.state = States.IDLE
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)
    sm._current_round_path = agentflow_dir / "current_round.json"
    sm._tasks_in_flight_path = agentflow_dir / "tasks_in_flight.json"
    sm._log_audit = MagicMock()
    ep = tmp_path / "execution_plan.md"
    ep.write_text(ep_content, encoding="utf-8")
    return sm, ep


# ---------------------------------------------------------------------------
# Unit tests for _archive_oldest_merged_round
# ---------------------------------------------------------------------------

class TestArchiveOldestMergedRound:
    def test_no_archival_when_three_or_fewer_merged(self, tmp_path):
        """With <= 3 merged rounds, nothing is archived."""
        content = _make_ep_with_rounds([
            ("R-1", True), ("R-2", True), ("R-3", True),
        ])
        sm, ep = _make_manager_with_ep(tmp_path, content)
        lines = ep.read_text("utf-8").splitlines(keepends=True)

        result = _archive_oldest_merged_round(sm, ep, lines)

        assert result == lines
        assert not (tmp_path / "execution_plan.archive.md").exists()

    def test_archives_oldest_when_four_merged(self, tmp_path):
        """With 4 merged rounds, the oldest is moved to the archive."""
        content = _make_ep_with_rounds([
            ("R-1", True), ("R-2", True), ("R-3", True), ("R-4", True),
        ])
        sm, ep = _make_manager_with_ep(tmp_path, content)
        lines = ep.read_text("utf-8").splitlines(keepends=True)

        result = _archive_oldest_merged_round(sm, ep, lines)

        # R-1 row removed from result
        round_rows = [ln for ln in result if "| R-" in ln and "MERGED" in ln]
        assert len(round_rows) == 3
        assert all("R-1" not in ln for ln in round_rows)

        # Archive file contains R-1
        archive = tmp_path / "execution_plan.archive.md"
        assert archive.exists()
        assert "R-1" in archive.read_text("utf-8")

    def test_archives_only_one_per_call(self, tmp_path):
        """With 5 merged rounds, only the single oldest is archived per call."""
        content = _make_ep_with_rounds([
            ("R-1", True), ("R-2", True), ("R-3", True),
            ("R-4", True), ("R-5", True),
        ])
        sm, ep = _make_manager_with_ep(tmp_path, content)
        lines = ep.read_text("utf-8").splitlines(keepends=True)

        result = _archive_oldest_merged_round(sm, ep, lines)

        # Still has 4 merged rounds after one call (one removed from 5)
        round_rows = [ln for ln in result if "| R-" in ln and "MERGED" in ln]
        assert len(round_rows) == 4

        archive = tmp_path / "execution_plan.archive.md"
        assert "R-1" in archive.read_text("utf-8")
        assert "R-2" not in archive.read_text("utf-8")

    def test_archive_appends_to_existing_file(self, tmp_path):
        """Archive file accumulates: subsequent calls append, not overwrite."""
        archive = tmp_path / "execution_plan.archive.md"
        archive.write_text("| R-0 | T-100 | old |— MERGED\n", encoding="utf-8")

        content = _make_ep_with_rounds([
            ("R-1", True), ("R-2", True), ("R-3", True), ("R-4", True),
        ])
        sm, ep = _make_manager_with_ep(tmp_path, content)
        lines = ep.read_text("utf-8").splitlines(keepends=True)

        _archive_oldest_merged_round(sm, ep, lines)

        archive_text = archive.read_text("utf-8")
        assert "R-0" in archive_text
        assert "R-1" in archive_text

    def test_task_rows_not_counted_as_merged_rounds(self, tmp_path):
        """Task rows (| T-NNN |) with MERGED are not counted as round rows."""
        content = (
            "# Plan\n\n"
            "| Round | Tasks | Status |\n|---|---|---|\n"
            "| R-1 | T-100 | note | — MERGED\n"
            "| R-2 | T-101 | note | — MERGED\n"
            "| R-3 | T-102 | note | — MERGED\n"
            "\n"
            "| Task | Title | Depends | Status |\n|---|---|---|---|\n"
            "| T-100 | Some task | — | MERGED |\n"
            "| T-101 | Other task | — | MERGED |\n"
        )
        sm, ep = _make_manager_with_ep(tmp_path, content)
        lines = ep.read_text("utf-8").splitlines(keepends=True)

        result = _archive_oldest_merged_round(sm, ep, lines)

        # 3 round rows, 2 task rows with MERGED — no archival needed
        assert result == lines
        assert not (tmp_path / "execution_plan.archive.md").exists()

    def test_idempotent_on_same_state(self, tmp_path):
        """Calling twice on same content removes the same (now-absent) row — safe."""
        content = _make_ep_with_rounds([
            ("R-1", True), ("R-2", True), ("R-3", True), ("R-4", True),
        ])
        sm, ep = _make_manager_with_ep(tmp_path, content)
        lines = ep.read_text("utf-8").splitlines(keepends=True)

        result1 = _archive_oldest_merged_round(sm, ep, lines)
        result2 = _archive_oldest_merged_round(sm, ep, result1)

        # Second call: only 3 remain, no further archival
        round_rows = [ln for ln in result2 if "| R-" in ln and "MERGED" in ln]
        assert len(round_rows) == 3

    def test_logs_audit_event_on_archive(self, tmp_path):
        """Archive action emits round_archive_written audit event."""
        content = _make_ep_with_rounds([
            ("R-1", True), ("R-2", True), ("R-3", True), ("R-4", True),
        ])
        sm, ep = _make_manager_with_ep(tmp_path, content)
        lines = ep.read_text("utf-8").splitlines(keepends=True)

        _archive_oldest_merged_round(sm, ep, lines)

        audit_calls = [c[0][0] for c in sm._log_audit.call_args_list]
        assert any(c.get("event") == "round_archive_written" for c in audit_calls)

    def test_no_merged_rounds_no_archival(self, tmp_path):
        """No merged rounds → returns lines unchanged, no archive."""
        content = _make_ep_with_rounds([
            ("R-1", False), ("R-2", False),
        ])
        sm, ep = _make_manager_with_ep(tmp_path, content)
        lines = ep.read_text("utf-8").splitlines(keepends=True)

        result = _archive_oldest_merged_round(sm, ep, lines)

        assert result == lines
        assert not (tmp_path / "execution_plan.archive.md").exists()

    def test_archive_write_error_returns_unchanged_lines(self, tmp_path):
        """If archive write fails, original lines are returned and error is logged."""
        content = _make_ep_with_rounds([
            ("R-1", True), ("R-2", True), ("R-3", True), ("R-4", True),
        ])
        sm, ep = _make_manager_with_ep(tmp_path, content)
        lines = ep.read_text("utf-8").splitlines(keepends=True)

        with patch("builtins.open", side_effect=OSError("disk full")):
            result = _archive_oldest_merged_round(sm, ep, lines)

        # Lines unchanged on error
        assert result == lines
        audit_calls = [c[0][0] for c in sm._log_audit.call_args_list]
        assert any(c.get("event") == "round_archive_error" for c in audit_calls)


# ---------------------------------------------------------------------------
# Integration tests: _write_merged_and_clear triggers archive + index rebuild
# ---------------------------------------------------------------------------

class TestWriteMergedAndClearWithArchive:
    def _setup(self, tmp_path, ep_content, round_id, task_ids):
        sm, ep = _make_manager_with_ep(tmp_path, ep_content)
        agentflow_dir = tmp_path / ".agentflow"
        sm._current_round_path.write_text(
            json.dumps({"round_id": round_id, "task_ids": task_ids}),
            encoding="utf-8",
        )
        sm._tasks_in_flight_path.write_text(json.dumps(task_ids), encoding="utf-8")
        sm._config = {"handoff_primary_tokens": 80000}
        return sm, ep

    def test_fourth_merged_round_triggers_archive(self, tmp_path):
        """Full flow: 3 existing merged rounds + 1 new → archive receives oldest."""
        ep_content = (
            "# Plan\n\n"
            "| Round | Tasks | Status |\n|---|---|---|\n"
            "| R-1 | T-001 | done | — MERGED\n"
            "| R-2 | T-002 | done | — MERGED\n"
            "| R-3 | T-003 | done | — MERGED\n"
            "| R-4 | T-004 | in progress |\n"
            "\n## Addendum: T-004\n"
        )
        sm, ep = self._setup(tmp_path, ep_content, "R-4", ["T-004"])

        with patch(
            "agentflow.shell.drain_restart.update_index",
        ) as mock_idx:
            _write_merged_and_clear(sm)

        ep_text = ep.read_text("utf-8")
        # R-4 marked merged in execution_plan.md
        assert "R-4" in ep_text
        assert "MERGED" in ep_text

        # R-1 archived
        archive = tmp_path / "execution_plan.archive.md"
        assert archive.exists()
        assert "R-1" in archive.read_text("utf-8")
        # R-1 not in main file
        assert "R-1" not in ep_text

        # Index rebuild called
        assert mock_idx.called

    def test_three_merged_rounds_no_archive(self, tmp_path):
        """Exactly 3 merged rounds after marking → no archive."""
        ep_content = (
            "# Plan\n\n"
            "| Round | Tasks | Status |\n|---|---|---|\n"
            "| R-1 | T-001 | done | — MERGED\n"
            "| R-2 | T-002 | done | — MERGED\n"
            "| R-3 | T-003 | in progress |\n"
            "\n## Addendum: T-003\n"
        )
        sm, ep = self._setup(tmp_path, ep_content, "R-3", ["T-003"])

        with patch("agentflow.shell.drain_restart.update_index"):
            _write_merged_and_clear(sm)

        archive = tmp_path / "execution_plan.archive.md"
        assert not archive.exists()

    def test_index_rebuild_called_after_archive(self, tmp_path):
        """Index rebuild is always triggered when a round is marked merged and archived."""
        ep_content = (
            "# Plan\n\n"
            "| Round | Tasks | Status |\n|---|---|---|\n"
            "| R-1 | T-001 | done | — MERGED\n"
            "| R-2 | T-002 | done | — MERGED\n"
            "| R-3 | T-003 | done | — MERGED\n"
            "| R-4 | T-004 | in progress |\n"
            "\n## Addendum: T-004\n"
        )
        sm, ep = self._setup(tmp_path, ep_content, "R-4", ["T-004"])

        calls = []
        with patch(
            "agentflow.shell.drain_restart.update_index",
            side_effect=lambda *a, **kw: calls.append(a),
        ):
            _write_merged_and_clear(sm)

        assert len(calls) >= 1
        # The call must target execution_plan.md
        targets = [str(a[1]) for a in calls]
        assert any("execution_plan.md" in t for t in targets)
