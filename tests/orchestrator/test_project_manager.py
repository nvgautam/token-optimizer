"""Tests for T-015: ProjectManager and MergeSequencer."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentflow.config.loader import load_config
from agentflow.orchestrator.dag import DAG
from agentflow.orchestrator.merge_sequencer import MergeSequencer
from agentflow.orchestrator.project_manager import ProjectManager
from agentflow.orchestrator.state import ProjectState, TaskStatus
from agentflow.reviewer.code_reviewer import CodeReviewFinding, ReviewResult
from agentflow.reviewer.security_reviewer import SecurityFinding, SecurityReviewResult
from agentflow.worker.agent_runner import WorkerResult, WorkerResultStatus


def _make_task(tid, depends_on=None, owns=None):
    return {
        "task_id": tid,
        "title": f"Task {tid}",
        "description": "desc",
        "owns": owns or [f"src/{tid}.py"],
        "reads": [],
        "depends_on": depends_on or [],
        "test_requirements": {"unit": [], "integration": [], "coverage_threshold": 85},
        "security_constraints": [],
        "acceptance_criteria": "tests green",
        "estimated_lines": 100,
        "context_section": "architecture.md#overview",
    }


def _make_tasks_json(tasks, tmp_path):
    data = {"project": "test", "version": "1.0", "tasks": tasks}
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(data))
    return path


def _make_pm(tmp_path, tasks, config=None):
    _make_tasks_json(tasks, tmp_path)
    cfg = config or load_config(tmp_path)
    return ProjectManager(tmp_path, cfg)


# --- ProjectManager tests ---

def test_ready_tasks_spawned_up_to_parallelism(tmp_path):
    tasks = [_make_task("A"), _make_task("B"), _make_task("C"), _make_task("D"), _make_task("E")]
    _make_tasks_json(tasks, tmp_path)
    cfg = load_config(tmp_path)
    cfg.parallelism = 2

    results = [
        WorkerResult("A", WorkerResultStatus.PR_OPENED, 1, 100, 0, "ok"),
        WorkerResult("B", WorkerResultStatus.PR_OPENED, 2, 100, 0, "ok"),
    ]
    call_count = []

    def fake_run_worker(task, *args, **kwargs):
        call_count.append(task["task_id"])
        return results.pop(0) if results else WorkerResult(
            task["task_id"], WorkerResultStatus.ERROR, None, 0, 0, "err"
        )

    with patch("agentflow.orchestrator.project_manager.run_worker", side_effect=fake_run_worker), \
         patch("agentflow.orchestrator.project_manager.review_pr", return_value=ReviewResult(1, 0, {"CRITICAL": 0, "HIGH": 0, "LOW": 0}, [], False)), \
         patch("agentflow.orchestrator.project_manager.review_security", return_value=SecurityReviewResult(1, 0, 0, [], False)):
        pm = ProjectManager(tmp_path, cfg)
        # only run one iteration by patching start to limit scope
        pm._spawn_batch(["A", "B"], {t["task_id"]: t for t in tasks}, {})

    assert len(call_count) == 2
    assert "A" in call_count and "B" in call_count


def test_task_with_unmet_dependency_not_spawned(tmp_path):
    tasks = [_make_task("A"), _make_task("B", depends_on=["A"])]
    _make_tasks_json(tasks, tmp_path)
    cfg = load_config(tmp_path)
    pm = ProjectManager(tmp_path, cfg)

    # merged_ids is empty — B's dep A is not merged
    ready = pm._dag.ready_tasks(set())
    assert "A" in ready
    assert "B" not in ready


def test_escalated_result_writes_escalation_file(tmp_path):
    tasks = [_make_task("A")]
    pm = _make_pm(tmp_path, tasks)

    result = WorkerResult("A", WorkerResultStatus.ESCALATED, None, 0, 2, "too many restarts")
    pm._handle_worker_result(result, tasks[0], {})

    esc_file = tmp_path / ".agentflow" / "escalations" / "A.md"
    assert esc_file.exists()
    assert "too many restarts" in esc_file.read_text()


def test_critical_security_finding_causes_rework_needed(tmp_path):
    tasks = [_make_task("A")]
    pm = _make_pm(tmp_path, tasks)
    pm._state.transition("A", TaskStatus.SPAWNED)
    pm._state.transition("A", TaskStatus.IMPLEMENTING)

    sec_result = SecurityReviewResult(1, 1, 0, [], False)  # critical_count=1
    code_result = ReviewResult(1, 0, {"CRITICAL": 0}, [], False)

    with patch.object(pm, "_run_reviewer_pipeline", return_value=(code_result, sec_result)):
        result = WorkerResult("A", WorkerResultStatus.PR_OPENED, 42, 500, 0, "ok")
        pm._handle_worker_result(result, tasks[0], {})

    assert pm._state.get("A").status == TaskStatus.REWORK_NEEDED


def test_critical_code_review_causes_rework_needed(tmp_path):
    tasks = [_make_task("A")]
    pm = _make_pm(tmp_path, tasks)
    pm._state.transition("A", TaskStatus.SPAWNED)
    pm._state.transition("A", TaskStatus.IMPLEMENTING)

    code_result = ReviewResult(1, 1, {"CRITICAL": 1}, [], False)
    sec_result = SecurityReviewResult(1, 0, 0, [], False)

    with patch.object(pm, "_run_reviewer_pipeline", return_value=(code_result, sec_result)):
        result = WorkerResult("A", WorkerResultStatus.PR_OPENED, 42, 500, 0, "ok")
        pm._handle_worker_result(result, tasks[0], {})

    assert pm._state.get("A").status == TaskStatus.REWORK_NEEDED


def test_clean_reviews_cause_review_passed(tmp_path):
    tasks = [_make_task("A")]
    pm = _make_pm(tmp_path, tasks)
    pm._state.transition("A", TaskStatus.SPAWNED)
    pm._state.transition("A", TaskStatus.IMPLEMENTING)

    code_result = ReviewResult(1, 0, {"CRITICAL": 0, "HIGH": 0}, [], False)
    sec_result = SecurityReviewResult(1, 0, 0, [], False)

    with patch.object(pm, "_run_reviewer_pipeline", return_value=(code_result, sec_result)):
        result = WorkerResult("A", WorkerResultStatus.PR_OPENED, 42, 500, 0, "ok")
        pm._handle_worker_result(result, tasks[0], {})

    assert pm._state.get("A").status == TaskStatus.REVIEW_PASSED


def test_status_returns_string_with_task_ids(tmp_path):
    tasks = [_make_task("A"), _make_task("B")]
    pm = _make_pm(tmp_path, tasks)
    s = pm.status()
    assert "A" in s
    assert "B" in s
    assert "PENDING" in s


# --- MergeSequencer tests ---

def _make_sequencer(tmp_path):
    tasks = [_make_task("A"), _make_task("B", depends_on=["A"])]
    _make_tasks_json(tasks, tmp_path)
    cfg = load_config(tmp_path)
    state = ProjectState(tmp_path)
    state.initialise(["A", "B"])
    dag = DAG.from_file(tmp_path / "tasks.json")
    seq = MergeSequencer(tmp_path, cfg, state)
    return seq, dag, state


def test_merge_task_calls_delete_worktree_on_success(tmp_path):
    seq, dag, state = _make_sequencer(tmp_path)
    state.transition("A", TaskStatus.SPAWNED)
    state.transition("A", TaskStatus.IMPLEMENTING)
    state.transition("A", TaskStatus.PR_OPEN)
    state.transition("A", TaskStatus.REVIEW_IN_PROGRESS)
    state.transition("A", TaskStatus.REVIEW_PASSED)
    state.transition("A", TaskStatus.HUMAN_APPROVED)

    with patch("agentflow.orchestrator.merge_sequencer.subprocess.run") as mock_run, \
         patch("agentflow.orchestrator.merge_sequencer.delete_worktree") as mock_del:
        mock_run.return_value = MagicMock(returncode=0)
        result = seq.merge_task("A", dag)

    assert result is True
    mock_del.assert_called_once()


def test_merge_task_returns_false_on_git_error(tmp_path):
    seq, dag, state = _make_sequencer(tmp_path)

    import subprocess as sp
    abort_mock = MagicMock(returncode=0)
    with patch("agentflow.orchestrator.merge_sequencer.subprocess.run") as mock_run:
        # first call (merge) raises, second call (abort) succeeds
        mock_run.side_effect = [
            sp.CalledProcessError(1, "git", stderr=b"conflict"),
            abort_mock,
        ]
        result = seq.merge_task("A", dag)

    assert result is False
    assert state.get("A").status == TaskStatus.PENDING


def test_merge_all_approved_processes_in_topological_order(tmp_path):
    seq, dag, state = _make_sequencer(tmp_path)
    merged_order = []

    def fake_merge(task_id, d):
        merged_order.append(task_id)
        return True

    for tid in ["A", "B"]:
        s = state.get(tid)
        for to in [TaskStatus.SPAWNED, TaskStatus.IMPLEMENTING, TaskStatus.PR_OPEN,
                   TaskStatus.REVIEW_IN_PROGRESS, TaskStatus.REVIEW_PASSED, TaskStatus.HUMAN_APPROVED]:
            state.transition(tid, to)

    with patch.object(seq, "merge_task", side_effect=fake_merge):
        seq.merge_all_approved(dag, state)

    assert merged_order.index("A") < merged_order.index("B")
