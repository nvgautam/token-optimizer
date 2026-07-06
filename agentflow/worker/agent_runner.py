"""Headless Anthropic API agent runner for a single AgentFlow task."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from agentflow.config.schema import AgentFlowConfig
from agentflow.telemetry.token_tracker import TokenTracker, BudgetStatus

MAX_RESTARTS = 2

WORKER_TOOLS = [
    {"name": "read_file", "description": "Read a file from the project",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write content to an owned file",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "run_tests", "description": "Run test suite and return results",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "open_pr", "description": "Open a PR when all tests pass",
     "input_schema": {"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"}}, "required": ["title", "body"]}},
]


class WorkerResultStatus(Enum):
    PR_OPENED = "pr_opened"
    ESCALATED = "escalated"
    ERROR = "error"


@dataclass
class WorkerResult:
    task_id: str
    status: WorkerResultStatus
    pr_number: int | None
    tokens_consumed: int
    restarts: int
    message: str


class _WorkerSession:
    def __init__(self, task: dict, project_root: Path, worktree_path: Path,
                 config: AgentFlowConfig, tracker: TokenTracker, client: Any) -> None:
        self._task = task
        self._project_root = project_root
        self._worktree_path = worktree_path
        self._config = config
        self._tracker = tracker
        self._client = client
        self._task_id = task["task_id"]
        self._owns: set[str] = set(task.get("owns", []))
        self.files_written: list[str] = []
        self._last_test_ok = False

    def run(self, opening_message: str) -> tuple[str, int | None]:
        messages = [{"role": "user", "content": opening_message}]
        while True:
            response = self._client.messages.create(
                model=self._config.models.worker, max_tokens=4096,
                tools=WORKER_TOOLS, messages=messages,
            )
            budget = self._tracker.track_span(
                self._task_id, "worker.api_call",
                response.usage.input_tokens, response.usage.output_tokens,
            )
            if budget.status == BudgetStatus.EXCEEDED:
                return "budget_exceeded", None
            if response.stop_reason == "end_turn":
                return "no_pr", None

            tool_results = []
            pr_number = None
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = self._dispatch(block.name, block.input)
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(result)})
                if block.name == "open_pr" and isinstance(result, int):
                    pr_number = result
            if pr_number is not None:
                return "pr_opened", pr_number
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

    def _dispatch(self, name: str, inputs: dict) -> Any:
        if name == "read_file":
            return self._read(inputs["path"])
        if name == "write_file":
            return self._write(inputs["path"], inputs["content"])
        if name == "run_tests":
            return self._tests()
        if name == "open_pr":
            return self._pr(inputs["title"], inputs["body"])
        return f"Unknown tool: {name}"

    def _read(self, path_str: str) -> str:
        try:
            target = (self._project_root / path_str).resolve()
            if not str(target).startswith(str(self._project_root.resolve())):
                return "Error: path traversal not allowed"
            return target.read_text() if target.exists() else f"Error: not found: {path_str}"
        except Exception as exc:
            return f"Error: {exc}"

    def _write(self, path_str: str, content: str) -> str:
        if path_str not in self._owns:
            return f"Error: {path_str!r} is not owned by this task"
        try:
            target = self._worktree_path / path_str
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            if path_str not in self.files_written:
                self.files_written.append(path_str)
            return f"Written: {path_str}"
        except Exception as exc:
            return f"Error: {exc}"

    def _tests(self) -> str:
        from agentflow.tools.test_runner import run_tests
        r = run_tests(self._worktree_path, self._config)
        self._last_test_ok = r.coverage_ok and r.status == "ok"
        return (f"status={r.status} passed={r.passed} failed={r.failed} "
                f"coverage={r.coverage_pct}% ok={r.coverage_ok}\n{r.output[:800]}")

    def _pr(self, title: str, body: str) -> Any:
        if not self._last_test_ok:
            return "Error: tests must pass with coverage_ok=True before opening PR"
        try:
            from agentflow.tools.git import commit_files, push_branch
            from agentflow.tools.github import create_pr
            
            # Commit the written files
            files_to_commit = [self._worktree_path / f for f in self.files_written]
            if files_to_commit:
                commit_files(self._worktree_path, f"Implement task {self._task_id}", files_to_commit)
                
            # Push the branch
            push_branch(self._worktree_path, f"task/{self._task_id}")
            
            repo = os.environ.get("AGENTFLOW_REPO", "owner/repo")
            return create_pr(repo, f"task/{self._task_id}", "main", title, body)
        except Exception as exc:
            return f"Error: {exc}"


def run_worker(task: dict, project_root: Path, worktree_path: Path,
               config: AgentFlowConfig) -> WorkerResult:
    """Run a headless agent for a task. Never raises — always returns WorkerResult."""
    task_id = task["task_id"]
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return WorkerResult(task_id, WorkerResultStatus.ERROR, None, 0, 0, "ANTHROPIC_API_KEY not set")

    try:
        from agentflow.tools.git import create_worktree
        create_worktree(project_root, task_id, f"task/{task_id}")
    except Exception as exc:
        return WorkerResult(task_id, WorkerResultStatus.ERROR, None, 0, 0, f"Failed to create worktree: {exc}")

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        tracker = TokenTracker(project_root, config)
        bundle_path = project_root / ".agentflow" / "context" / f"{task_id}.md"
        opening = bundle_path.read_text() if bundle_path.exists() else (
            f"Implement task {task_id}: {task.get('description', '')}")

        restarts = 0
        while True:
            session = _WorkerSession(task, project_root, worktree_path, config, tracker, client)
            outcome, pr_number = session.run(opening)

            if outcome == "pr_opened":
                tracker.close_session(task_id, status="pr_opened")
                return WorkerResult(task_id, WorkerResultStatus.PR_OPENED, pr_number,
                                    tracker.session_total(task_id), restarts, f"PR #{pr_number} opened")

            if outcome == "budget_exceeded":
                if restarts >= MAX_RESTARTS:
                    tracker.close_session(task_id, status="escalated")
                    return WorkerResult(task_id, WorkerResultStatus.ESCALATED, None,
                                        tracker.session_total(task_id), restarts,
                                        f"Budget exceeded after {restarts} restarts")
                restarts += 1
                files_done = ", ".join(session.files_written) or "none"
                opening = (f"Restart {restarts}/{MAX_RESTARTS}. Files written: {files_done}.\n\n{opening}")
                continue

            tracker.close_session(task_id, status="no_pr")
            return WorkerResult(task_id, WorkerResultStatus.ESCALATED, None,
                                tracker.session_total(task_id), restarts,
                                "Agent stopped without opening a PR")

    except Exception as exc:
        return WorkerResult(task_id, WorkerResultStatus.ERROR, None, 0, 0, f"Unexpected error: {exc}")

