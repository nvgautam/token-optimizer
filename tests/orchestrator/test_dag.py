"""Tests for T-008: DAG builder and validator."""

import json
import pytest
from pathlib import Path

from agentflow.orchestrator.dag import DAG, CyclicDependencyError, OwnershipConflictError


def make_task(task_id, owns=None, depends_on=None):
    return {
        "task_id": task_id,
        "owns": owns or [f"src/{task_id}.py"],
        "reads": [],
        "depends_on": depends_on or [],
    }


def test_dag_rejects_shared_owned_file():
    tasks = [
        make_task("A", owns=["src/shared.py"]),
        make_task("B", owns=["src/shared.py"]),
    ]
    with pytest.raises(OwnershipConflictError) as exc_info:
        DAG(tasks)
    assert "src/shared.py" in str(exc_info.value)
    assert "A" in exc_info.value.task_ids
    assert "B" in exc_info.value.task_ids


def test_topological_order_respects_dependencies():
    tasks = [
        make_task("B", depends_on=["A"]),
        make_task("A"),
    ]
    dag = DAG(tasks)
    order = dag.topological_order()
    assert order.index("A") < order.index("B")


def test_cyclic_dependency_raises():
    tasks = [
        make_task("A", depends_on=["B"]),
        make_task("B", depends_on=["A"]),
    ]
    with pytest.raises(CyclicDependencyError):
        DAG(tasks)


def test_ready_tasks_returns_tasks_with_completed_deps():
    tasks = [
        make_task("A"),
        make_task("B", depends_on=["A"]),
        make_task("C", depends_on=["A"]),
    ]
    dag = DAG(tasks)
    assert set(dag.ready_tasks({"A"})) == {"B", "C"}


def test_ready_tasks_excludes_already_completed():
    tasks = [make_task("A"), make_task("B")]
    dag = DAG(tasks)
    ready = dag.ready_tasks({"A"})
    assert "A" not in ready
    assert "B" in ready


def test_unknown_depends_on_raises_value_error():
    tasks = [make_task("A", depends_on=["GHOST"])]
    with pytest.raises(ValueError, match="GHOST"):
        DAG(tasks)


def test_no_dependencies_all_tasks_ready():
    tasks = [make_task("A"), make_task("B"), make_task("C")]
    dag = DAG(tasks)
    assert set(dag.ready_tasks(set())) == {"A", "B", "C"}


def test_from_file_loads_correctly(tmp_path):
    tasks_data = {"tasks": [make_task("A"), make_task("B", depends_on=["A"])]}
    f = tmp_path / "tasks.json"
    f.write_text(json.dumps(tasks_data))
    dag = DAG.from_file(f)
    order = dag.topological_order()
    assert order.index("A") < order.index("B")


def test_three_level_chain_order():
    tasks = [
        make_task("C", depends_on=["B"]),
        make_task("B", depends_on=["A"]),
        make_task("A"),
    ]
    dag = DAG(tasks)
    order = dag.topological_order()
    assert order.index("A") < order.index("B") < order.index("C")
