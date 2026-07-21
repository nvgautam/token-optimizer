"""Tests for agentflow.bundle — deterministic ctx bundle assembly."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from agentflow.bundle import assemble_bundle


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Fake project_root with tasks.json, execution_plan.md, and skill stubs."""
    (tmp_path / "tasks.json").write_text(json.dumps({"tasks": [
        {"task_id": "T-001", "status": "complete"},
        {"task_id": "T-010", "status": "pending"},
        {"task_id": "T-999", "status": "pending"},
    ]}))
    (tmp_path / "execution_plan.md").write_text(textwrap.dedent("""\
        ## Some section
        Not an addendum.

        ## Addendum: T-010 — My task title
        This is the addendum for T-010.
        It spans multiple lines.

        ## Next section
        Not part of T-010 addendum.
    """))
    worker_dir = tmp_path / "commands" / "claude" / "worker"
    worker_dir.mkdir(parents=True)
    (worker_dir / "system.md").write_text("# Worker System Prompt\nworker-content")
    (worker_dir / "testing_guide.md").write_text("# Testing Guide\ntesting-content")
    reviewer_dir = tmp_path / "commands" / "claude" / "reviewer"
    reviewer_dir.mkdir(parents=True)
    (reviewer_dir / "code_review.md").write_text("# Code Review\nreviewer-content")
    return tmp_path


def _out(tmp_path: Path) -> Path:
    d = tmp_path / "out"
    d.mkdir(exist_ok=True)
    return d


def test_worker_bundle(project: Path, tmp_path: Path) -> None:
    path = assemble_bundle("T-001", "worker", project, _out(tmp_path))
    payload = json.loads(path.read_text())
    assert payload["task_id"] == "T-001"
    assert payload["agent_type"] == "worker"
    assert payload["status"] == "complete"
    assert "worker-content" in payload["system_prompt"]
    assert "assembled_at" in payload


def test_reviewer_bundle(project: Path, tmp_path: Path) -> None:
    payload = json.loads(
        assemble_bundle("T-001", "reviewer", project, _out(tmp_path)).read_text()
    )
    assert payload["agent_type"] == "reviewer"
    assert "reviewer-content" in payload["system_prompt"]


def test_test_bundle(project: Path, tmp_path: Path) -> None:
    payload = json.loads(
        assemble_bundle("T-001", "test", project, _out(tmp_path)).read_text()
    )
    assert payload["agent_type"] == "test"
    assert "testing-content" in payload["system_prompt"]


def test_missing_task_raises(project: Path, tmp_path: Path) -> None:
    out = _out(tmp_path)
    with pytest.raises(ValueError, match="T-MISSING"):
        assemble_bundle("T-MISSING", "worker", project, out)
    assert list(out.iterdir()) == []


def test_idempotent(project: Path, tmp_path: Path) -> None:
    out = _out(tmp_path)
    p1 = assemble_bundle("T-001", "worker", project, out)
    p2 = assemble_bundle("T-001", "worker", project, out)
    assert p1 == p2
    assert p1.read_text() == p2.read_text()


def test_addendum_found(project: Path, tmp_path: Path) -> None:
    payload = json.loads(
        assemble_bundle("T-010", "worker", project, _out(tmp_path)).read_text()
    )
    assert payload["addendum"] != ""
    assert "addendum for T-010" in payload["addendum"]
    assert "spans multiple lines" in payload["addendum"]
    assert "Next section" not in payload["addendum"]


def test_addendum_absent(project: Path, tmp_path: Path) -> None:
    payload = json.loads(
        assemble_bundle("T-999", "worker", project, _out(tmp_path)).read_text()
    )
    assert payload["addendum"] == ""


def test_output_filename_format(project: Path, tmp_path: Path) -> None:
    path = assemble_bundle("T-001", "worker", project, _out(tmp_path))
    name = path.name
    assert name.startswith("ctx-T-001-")
    assert name.endswith(".json")
    hash_part = name[len("ctx-T-001-"):-len(".json")]
    assert len(hash_part) == 8
    assert all(c in "0123456789abcdef" for c in hash_part)
