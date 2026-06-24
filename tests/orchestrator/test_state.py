"""Tests for T-008: ProjectState persistent state machine."""

import json
import pytest
from pathlib import Path

from agentflow.orchestrator.state import (
    ProjectState,
    TaskStatus,
    InvalidTransitionError,
)


@pytest.fixture
def state(tmp_path):
    return ProjectState(tmp_path)


@pytest.fixture
def initialised_state(tmp_path):
    ps = ProjectState(tmp_path)
    ps.initialise(["T-001", "T-002"])
    return ps, tmp_path


def test_transition_pending_to_spawned_writes_timestamp(initialised_state):
    ps, cwd = initialised_state
    ts = ps.transition("T-001", TaskStatus.SPAWNED)
    assert ts.status == TaskStatus.SPAWNED
    assert ts.updated_at  # non-empty ISO string
    data = json.loads((cwd / ".agentflow" / "state.json").read_text())
    task = next(t for t in data["tasks"] if t["task_id"] == "T-001")
    assert task["status"] == "SPAWNED"


def test_invalid_transition_raises(initialised_state):
    ps, _ = initialised_state
    with pytest.raises(InvalidTransitionError) as exc_info:
        ps.transition("T-001", TaskStatus.PENDING)
    assert exc_info.value.task_id == "T-001"
    assert exc_info.value.from_status == TaskStatus.PENDING
    assert exc_info.value.to_status == TaskStatus.PENDING


def test_spawned_to_pending_raises(initialised_state):
    ps, _ = initialised_state
    ps.transition("T-001", TaskStatus.SPAWNED)
    with pytest.raises(InvalidTransitionError):
        ps.transition("T-001", TaskStatus.PENDING)


def test_state_persists_across_instances(tmp_path):
    ps1 = ProjectState(tmp_path)
    ps1.initialise(["T-001"])
    ps1.transition("T-001", TaskStatus.SPAWNED)

    ps2 = ProjectState(tmp_path)
    assert ps2.get("T-001").status == TaskStatus.SPAWNED


def test_load_state_empty_when_file_absent(tmp_path):
    ps = ProjectState(tmp_path)
    assert ps.all_tasks() == []


def test_initialise_sets_all_tasks_to_pending(initialised_state):
    ps, _ = initialised_state
    for ts in ps.all_tasks():
        assert ts.status == TaskStatus.PENDING


def test_get_raises_key_error_for_unknown_task(state):
    with pytest.raises(KeyError, match="GHOST"):
        state.get("GHOST")


def test_transition_stores_pr_number(initialised_state):
    ps, _ = initialised_state
    ps.transition("T-001", TaskStatus.SPAWNED)
    ps.transition("T-001", TaskStatus.IMPLEMENTING)
    ps.transition("T-001", TaskStatus.PR_OPEN, pr_number=42)
    assert ps.get("T-001").pr_number == 42


def test_rework_count_stored_on_transition(initialised_state):
    ps, _ = initialised_state
    ps.transition("T-001", TaskStatus.SPAWNED)
    ps.transition("T-001", TaskStatus.IMPLEMENTING)
    ps.transition("T-001", TaskStatus.PR_OPEN)
    ps.transition("T-001", TaskStatus.REVIEW_IN_PROGRESS)
    ps.transition("T-001", TaskStatus.REWORK_NEEDED, rework_count=1)
    assert ps.get("T-001").rework_count == 1


def test_full_happy_path(initialised_state):
    ps, _ = initialised_state
    for status in [
        TaskStatus.SPAWNED,
        TaskStatus.IMPLEMENTING,
        TaskStatus.PR_OPEN,
        TaskStatus.REVIEW_IN_PROGRESS,
        TaskStatus.REVIEW_PASSED,
        TaskStatus.HUMAN_APPROVED,
        TaskStatus.MERGED,
    ]:
        ps.transition("T-001", status)
    assert ps.get("T-001").status == TaskStatus.MERGED


def test_state_json_contains_no_long_strings(initialised_state):
    ps, cwd = initialised_state
    data = (cwd / ".agentflow" / "state.json").read_text()
    for line in data.splitlines():
        assert len(line) < 200, f"Suspiciously long line: {line[:80]}..."
