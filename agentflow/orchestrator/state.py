"""Persistent task state machine for AgentFlow orchestrator."""

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class TaskStatus(Enum):
    PENDING = "PENDING"
    SPAWNED = "SPAWNED"
    IMPLEMENTING = "IMPLEMENTING"
    PR_OPEN = "PR_OPEN"
    REVIEW_IN_PROGRESS = "REVIEW_IN_PROGRESS"
    REWORK_NEEDED = "REWORK_NEEDED"
    REVIEW_PASSED = "REVIEW_PASSED"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    MERGED = "MERGED"


_VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.SPAWNED},
    TaskStatus.SPAWNED: {TaskStatus.IMPLEMENTING},
    TaskStatus.IMPLEMENTING: {TaskStatus.PR_OPEN},
    TaskStatus.PR_OPEN: {TaskStatus.REVIEW_IN_PROGRESS},
    TaskStatus.REVIEW_IN_PROGRESS: {TaskStatus.REWORK_NEEDED, TaskStatus.REVIEW_PASSED},
    TaskStatus.REWORK_NEEDED: {TaskStatus.IMPLEMENTING},
    TaskStatus.REVIEW_PASSED: {TaskStatus.HUMAN_APPROVED},
    TaskStatus.HUMAN_APPROVED: {TaskStatus.MERGED},
    TaskStatus.MERGED: set(),
}


class InvalidTransitionError(Exception):
    def __init__(self, task_id: str, from_status: TaskStatus, to_status: TaskStatus):
        self.task_id = task_id
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Task '{task_id}': invalid transition {from_status.value} → {to_status.value}"
        )


@dataclass
class TaskState:
    task_id: str
    status: TaskStatus
    updated_at: str
    tokens_consumed: int = 0
    pr_number: int | None = None
    rework_count: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TaskState":
        return cls(
            task_id=d["task_id"],
            status=TaskStatus(d["status"]),
            updated_at=d["updated_at"],
            tokens_consumed=d.get("tokens_consumed", 0),
            pr_number=d.get("pr_number"),
            rework_count=d.get("rework_count", 0),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectState:
    def __init__(self, cwd: Path):
        self._path = cwd / ".agentflow" / "state.json"
        self._tasks: dict[str, TaskState] = {}
        self.load_state()

    def load_state(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
            self._tasks = {
                item["task_id"]: TaskState.from_dict(item)
                for item in data.get("tasks", [])
            }
        except (json.JSONDecodeError, KeyError):
            self._tasks = {}

    def save_state(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        payload = {"tasks": [ts.to_dict() for ts in self._tasks.values()]}
        tmp.write_text(json.dumps(payload, indent=2))
        os.rename(tmp, self._path)

    def initialise(self, task_ids: list[str]) -> None:
        if self._tasks:
            raise RuntimeError("Cannot initialise: state already contains tasks")
        now = _now_iso()
        for tid in task_ids:
            self._tasks[tid] = TaskState(
                task_id=tid, status=TaskStatus.PENDING, updated_at=now
            )
        self.save_state()

    def transition(
        self, task_id: str, to_status: TaskStatus, **kwargs
    ) -> TaskState:
        ts = self.get(task_id)
        allowed = _VALID_TRANSITIONS.get(ts.status, set())
        if to_status not in allowed:
            raise InvalidTransitionError(task_id, ts.status, to_status)
        ts.status = to_status
        ts.updated_at = _now_iso()
        for k, v in kwargs.items():
            if hasattr(ts, k):
                setattr(ts, k, v)
        self.save_state()
        return ts

    def get(self, task_id: str) -> TaskState:
        if task_id not in self._tasks:
            raise KeyError(f"Unknown task_id: '{task_id}'")
        return self._tasks[task_id]

    def all_tasks(self) -> list[TaskState]:
        return list(self._tasks.values())
