"""DAG builder and validator for AgentFlow task graphs."""

import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path


class CyclicDependencyError(Exception):
    pass


class OwnershipConflictError(Exception):
    def __init__(self, file: str, task_ids: list[str]):
        self.file = file
        self.task_ids = task_ids
        super().__init__(f"File '{file}' claimed by multiple tasks: {task_ids}")


@dataclass
class TaskNode:
    task_id: str
    owns: list[str]
    reads: list[str]
    depends_on: list[str]
    title: str = ""
    description: str = ""
    test_requirements: dict = field(default_factory=dict)
    security_constraints: list[str] = field(default_factory=list)
    acceptance_criteria: str = ""
    estimated_lines: int = 0
    context_section: str = ""


class DAG:
    def __init__(self, tasks: list[dict]):
        self._nodes: dict[str, TaskNode] = {}
        self._build(tasks)
        self._validate_ownership()
        self._validate_dependencies()

    def _build(self, tasks: list[dict]) -> None:
        for t in tasks:
            node = TaskNode(
                task_id=t["task_id"],
                owns=t.get("owns", []),
                reads=t.get("reads", []),
                depends_on=t.get("depends_on", []),
                title=t.get("title", ""),
                description=t.get("description", ""),
                test_requirements=t.get("test_requirements", {}),
                security_constraints=t.get("security_constraints", []),
                acceptance_criteria=t.get("acceptance_criteria", ""),
                estimated_lines=t.get("estimated_lines", 0),
                context_section=t.get("context_section", ""),
            )
            self._nodes[node.task_id] = node

    def _validate_ownership(self) -> None:
        ownership: dict[str, list[str]] = defaultdict(list)
        for node in self._nodes.values():
            for f in node.owns:
                ownership[f].append(node.task_id)
        for f, owners in ownership.items():
            if len(owners) > 1:
                raise OwnershipConflictError(f, owners)

    def _validate_dependencies(self) -> None:
        known = set(self._nodes)
        for node in self._nodes.values():
            for dep in node.depends_on:
                if dep not in known:
                    raise ValueError(
                        f"Task '{node.task_id}' depends on unknown task '{dep}'"
                    )
        # detect cycles via Kahn's — if we can't drain the graph, there's a cycle
        in_degree = {tid: 0 for tid in self._nodes}
        for node in self._nodes.values():
            for dep in node.depends_on:
                in_degree[node.task_id] += 1

        queue = deque(tid for tid, deg in in_degree.items() if deg == 0)
        visited = 0
        while queue:
            tid = queue.popleft()
            visited += 1
            for node in self._nodes.values():
                if tid in node.depends_on:
                    in_degree[node.task_id] -= 1
                    if in_degree[node.task_id] == 0:
                        queue.append(node.task_id)

        if visited != len(self._nodes):
            raise CyclicDependencyError(
                "Dependency cycle detected in task graph"
            )

    def topological_order(self) -> list[str]:
        in_degree = {tid: 0 for tid in self._nodes}
        for node in self._nodes.values():
            for dep in node.depends_on:
                in_degree[node.task_id] += 1

        queue = deque(sorted(tid for tid, deg in in_degree.items() if deg == 0))
        result = []
        while queue:
            tid = queue.popleft()
            result.append(tid)
            dependents = [
                n.task_id for n in self._nodes.values() if tid in n.depends_on
            ]
            for dep_tid in sorted(dependents):
                in_degree[dep_tid] -= 1
                if in_degree[dep_tid] == 0:
                    queue.append(dep_tid)
        return result

    def ready_tasks(self, completed: set[str]) -> list[str]:
        return [
            tid
            for tid, node in self._nodes.items()
            if tid not in completed
            and all(dep in completed for dep in node.depends_on)
        ]

    def get_node(self, task_id: str) -> TaskNode:
        return self._nodes[task_id]

    def all_task_ids(self) -> list[str]:
        return list(self._nodes.keys())

    @classmethod
    def from_file(cls, tasks_json_path: Path) -> "DAG":
        data = json.loads(tasks_json_path.read_text())
        return cls(data["tasks"])
