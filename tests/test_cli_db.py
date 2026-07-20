"""Tests for agentflow.cli_db — cmd_round_start."""
from __future__ import annotations
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentflow.cli_db import cmd_round_start


def _make_args(
    task_ids: list[str],
    round_id: str | None = "test-round",
    sid: str | None = "test-sid",
) -> argparse.Namespace:
    return argparse.Namespace(task_ids=task_ids, round_id=round_id, sid=sid)


@pytest.fixture(autouse=True)
def chdir_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run each test with tmp_path as the working directory."""
    monkeypatch.chdir(tmp_path)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_writes_current_round_json(self, tmp_path: Path) -> None:
        args = _make_args(["T-001", "T-002"])
        rc = cmd_round_start(args)

        assert rc == 0
        round_path = tmp_path / ".agentflow" / "current_round.json"
        assert round_path.exists(), "current_round.json not written"
        data = json.loads(round_path.read_text())
        assert data["round_id"] == "test-round"
        assert data["task_ids"] == ["T-001", "T-002"]
        assert data["session_id"] == "test-sid"
        assert data["estimated_lines_per_task"] == {}
        assert data["file_counts_per_task"] == {}
        assert "timestamp" in data

    def test_writes_tasks_in_flight_per_sid(self, tmp_path: Path) -> None:
        args = _make_args(["T-001", "T-002"])
        cmd_round_start(args)

        tif_path = tmp_path / ".agentflow" / "sessions" / "test-sid" / "tasks_in_flight.json"
        assert tif_path.exists(), "tasks_in_flight.json not written under session dir"
        data = json.loads(tif_path.read_text())
        assert data == ["T-001", "T-002"]

    def test_prints_round_id(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        args = _make_args(["T-001"])
        cmd_round_start(args)
        out = capsys.readouterr().out.strip()
        assert out == "test-round"

    def test_returns_zero(self, tmp_path: Path) -> None:
        args = _make_args(["T-001"])
        assert cmd_round_start(args) == 0

    def test_idempotent_overwrite(self, tmp_path: Path) -> None:
        """Running twice with the same args produces the same state (idempotent)."""
        args = _make_args(["T-001"])
        cmd_round_start(args)
        args2 = _make_args(["T-002"], round_id="test-round", sid="test-sid")
        cmd_round_start(args2)

        round_path = tmp_path / ".agentflow" / "current_round.json"
        data = json.loads(round_path.read_text())
        # Second call wins
        assert data["task_ids"] == ["T-002"]

    def test_timestamp_is_iso8601(self, tmp_path: Path) -> None:
        args = _make_args(["T-001"])
        cmd_round_start(args)
        round_path = tmp_path / ".agentflow" / "current_round.json"
        data = json.loads(round_path.read_text())
        # Should parse without raising
        datetime.fromisoformat(data["timestamp"])


# ---------------------------------------------------------------------------
# SID fallback to env var
# ---------------------------------------------------------------------------

class TestSidEnvFallback:
    def test_env_var_sid_used_when_arg_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AGENTFLOW_SESSION_ID", "env-sid")
        args = _make_args(["T-010"], sid=None)
        cmd_round_start(args)

        tif_path = tmp_path / ".agentflow" / "sessions" / "env-sid" / "tasks_in_flight.json"
        assert tif_path.exists(), "tasks_in_flight.json not written under env-sid session dir"
        data = json.loads(tif_path.read_text())
        assert data == ["T-010"]

        round_path = tmp_path / ".agentflow" / "current_round.json"
        round_data = json.loads(round_path.read_text())
        assert round_data["session_id"] == "env-sid"

    def test_arg_sid_takes_precedence_over_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AGENTFLOW_SESSION_ID", "env-sid")
        args = _make_args(["T-011"], sid="arg-sid")
        cmd_round_start(args)

        tif_path = tmp_path / ".agentflow" / "sessions" / "arg-sid" / "tasks_in_flight.json"
        assert tif_path.exists()
        # env-sid path should NOT exist
        assert not (tmp_path / ".agentflow" / "sessions" / "env-sid").exists()

    def test_empty_arg_sid_falls_back_to_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AGENTFLOW_SESSION_ID", "env-sid-2")
        # argparse default=None but simulate explicit empty string from CLI
        args = _make_args(["T-012"], sid="")
        cmd_round_start(args)

        # empty string is falsy -> falls back to env var
        tif_path = tmp_path / ".agentflow" / "sessions" / "env-sid-2" / "tasks_in_flight.json"
        assert tif_path.exists()


# ---------------------------------------------------------------------------
# Missing SID — legacy fallback
# ---------------------------------------------------------------------------

class TestMissingSidLegacyFallback:
    def test_no_sid_writes_to_agentflow_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
        args = _make_args(["T-020"], sid=None)
        cmd_round_start(args)

        tif_path = tmp_path / ".agentflow" / "tasks_in_flight.json"
        assert tif_path.exists(), "tasks_in_flight.json not at legacy root path"
        data = json.loads(tif_path.read_text())
        assert data == ["T-020"]

    def test_no_sid_session_id_empty_in_round_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
        args = _make_args(["T-021"], sid=None)
        cmd_round_start(args)

        round_path = tmp_path / ".agentflow" / "current_round.json"
        data = json.loads(round_path.read_text())
        assert data["session_id"] == ""

    def test_no_sid_sessions_dir_not_created(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
        args = _make_args(["T-022"], sid=None)
        cmd_round_start(args)

        sessions_dir = tmp_path / ".agentflow" / "sessions"
        assert not sessions_dir.exists(), "sessions dir should not be created for legacy path"


# ---------------------------------------------------------------------------
# Timestamp-slug round_id when --round-id omitted
# ---------------------------------------------------------------------------

class TestTimestampSlugRoundId:
    def test_generated_round_id_format(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        args = _make_args(["T-030"], round_id=None)
        cmd_round_start(args)

        out = capsys.readouterr().out.strip()
        assert out.startswith("round-"), f"expected 'round-' prefix, got {out!r}"
        # Format: round-YYYYMMDD-HHMMSS (19 chars total)
        assert len(out) == len("round-20260719-103600"), f"unexpected length: {out!r}"

    def test_generated_round_id_stored_in_json(self, tmp_path: Path) -> None:
        args = _make_args(["T-031"], round_id=None)
        cmd_round_start(args)

        round_path = tmp_path / ".agentflow" / "current_round.json"
        data = json.loads(round_path.read_text())
        assert data["round_id"].startswith("round-")

    def test_generated_round_id_matches_printed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        args = _make_args(["T-032"], round_id=None)
        cmd_round_start(args)

        out = capsys.readouterr().out.strip()
        round_path = tmp_path / ".agentflow" / "current_round.json"
        data = json.loads(round_path.read_text())
        assert data["round_id"] == out, "printed round_id must match stored round_id"


# ---------------------------------------------------------------------------
# CLI DB Task Commands
# ---------------------------------------------------------------------------

class TestCliDbTaskCommands:
    def test_task_start_writes_to_tif_file(self, tmp_path: Path) -> None:
        from agentflow.cli_db import cmd_task_start
        # Setup tasks.json so it lists the task_id
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-100"}]}))

        args = argparse.Namespace(task_id="T-100", sid="session-t-100")
        rc = cmd_task_start(args)
        assert rc == 0

        tif_path = tmp_path / ".agentflow" / "sessions" / "session-t-100" / "tasks_in_flight.json"
        assert tif_path.exists()
        assert json.loads(tif_path.read_text()) == ["T-100"]

    def test_task_done_drains_and_completes(self, tmp_path: Path) -> None:
        from agentflow.cli_db import cmd_task_start, cmd_task_done
        # Setup tasks.json
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-100"}]}))

        # Start task
        args_start = argparse.Namespace(task_id="T-100", sid="session-t-100")
        cmd_task_start(args_start)

        # Complete task
        args_done = argparse.Namespace(task_id="T-100", sid="session-t-100")
        rc = cmd_task_done(args_done)
        assert rc == 0

        tif_path = tmp_path / ".agentflow" / "sessions" / "session-t-100" / "tasks_in_flight.json"
        assert tif_path.exists()
        assert json.loads(tif_path.read_text()) == []

        complete_path = tmp_path / ".agentflow" / "sessions" / "session-t-100" / "task_complete.json"
        assert complete_path.exists()
        assert json.loads(complete_path.read_text()) == {"status": "complete"}

