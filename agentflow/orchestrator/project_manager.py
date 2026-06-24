"""Top-level orchestrator: drives the full task lifecycle from PENDING to MERGED."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from pathlib import Path

from agentflow.config.schema import AgentFlowConfig
from agentflow.orchestrator.dag import DAG
from agentflow.orchestrator.state import ProjectState, TaskStatus
from agentflow.orchestrator.merge_sequencer import MergeSequencer
from agentflow.reviewer.code_reviewer import review_pr, ReviewResult
from agentflow.reviewer.security_reviewer import review_security, SecurityReviewResult
from agentflow.telemetry.token_tracker import TokenTracker
from agentflow.worker.agent_runner import run_worker, WorkerResult, WorkerResultStatus

_WORKER_TIMEOUT = 3600  # 1 hour per worker


class ProjectManager:
    def __init__(self, project_root: Path, config: AgentFlowConfig):
        self.project_root = project_root
        self.config = config
        self._tasks_file = project_root / "tasks.json"
        self._dag = DAG.from_file(self._tasks_file)
        self._state = ProjectState(project_root)
        self._tracker = TokenTracker(project_root, config)
        self._sequencer = MergeSequencer(project_root, config, self._state)
        self._repo = self._load_repo()

        if not self._state.all_tasks():
            self._state.initialise(self._dag.all_task_ids())

    def _load_repo(self) -> str:
        cfg_path = self.project_root / ".agentflow" / "config.yaml"
        if cfg_path.exists():
            import yaml
            data = yaml.safe_load(cfg_path.read_text()) or {}
            return data.get("repo", "owner/repo")
        return "owner/repo"

    def _load_tasks_dict(self) -> dict[str, dict]:
        data = json.loads(self._tasks_file.read_text())
        return {t["task_id"]: t for t in data["tasks"]}

    def start(self) -> None:
        tasks_dict = self._load_tasks_dict()
        rework_counts: dict[str, int] = {}

        while True:
            all_states = self._state.all_tasks()
            terminal = {TaskStatus.MERGED}
            escalated = [s for s in all_states if s.status.value == "ESCALATED"]
            if escalated:
                break

            merged_ids = {s.task_id for s in all_states if s.status == TaskStatus.MERGED}
            ready = self._dag.ready_tasks(merged_ids)
            actionable = [
                tid for tid in ready
                if self._state.get(tid).status == TaskStatus.PENDING
            ]

            if not actionable and all(
                s.status in terminal for s in all_states
            ):
                break

            batch = actionable[: self.config.parallelism]
            if batch:
                self._spawn_batch(batch, tasks_dict, rework_counts)

            self._sequencer.merge_all_approved(self._dag, self._state)

            if not actionable and not batch:
                break

    def _spawn_batch(
        self, task_ids: list[str], tasks_dict: dict, rework_counts: dict
    ) -> None:
        for tid in task_ids:
            self._state.transition(tid, TaskStatus.SPAWNED)
            self._state.transition(tid, TaskStatus.IMPLEMENTING)

        with ThreadPoolExecutor(max_workers=len(task_ids)) as pool:
            futures = {
                pool.submit(
                    run_worker,
                    tasks_dict[tid],
                    self.project_root,
                    self.project_root / "workspaces" / tid,
                    self.config,
                ): tid
                for tid in task_ids
            }
            for future in as_completed(futures, timeout=_WORKER_TIMEOUT):
                tid = futures[future]
                try:
                    result: WorkerResult = future.result()
                except Exception as exc:
                    self._notify_escalation(tid, str(exc))
                    continue
                self._handle_worker_result(result, tasks_dict[tid], rework_counts)

    def _handle_worker_result(
        self, result: WorkerResult, task: dict, rework_counts: dict
    ) -> None:
        tid = result.task_id
        self._tracker.track_span(tid, "worker.complete", result.tokens_consumed, 0)

        if result.status == WorkerResultStatus.ESCALATED:
            self._notify_escalation(tid, result.message)
            return

        if result.status == WorkerResultStatus.ERROR:
            count = rework_counts.get(tid, 0)
            if count < 1:
                rework_counts[tid] = count + 1
                self._state.transition(tid, TaskStatus.PR_OPEN, pr_number=None)
                self._state.transition(tid, TaskStatus.REVIEW_IN_PROGRESS)
                self._state.transition(tid, TaskStatus.REWORK_NEEDED)
                self._state.transition(tid, TaskStatus.IMPLEMENTING)
            else:
                self._notify_escalation(tid, result.message)
            return

        self._state.transition(tid, TaskStatus.PR_OPEN, pr_number=result.pr_number)
        code_result, sec_result = self._run_reviewer_pipeline(task, result.pr_number or 0)

        self._state.transition(tid, TaskStatus.REVIEW_IN_PROGRESS)
        has_critical = (
            code_result.severity_distribution.get("CRITICAL", 0) > 0
            or sec_result.critical_count > 0
        )
        if has_critical:
            self._state.transition(tid, TaskStatus.REWORK_NEEDED)
        else:
            self._state.transition(tid, TaskStatus.REVIEW_PASSED)

    def _run_reviewer_pipeline(
        self, task: dict, pr_number: int
    ) -> tuple[ReviewResult, SecurityReviewResult]:
        diff = ""
        contract_paths: list[Path] = []
        arch_section = ""

        with ThreadPoolExecutor(max_workers=2) as pool:
            code_future = pool.submit(
                review_pr, self._repo, pr_number, diff, contract_paths, arch_section, self.config
            )
            sec_future = pool.submit(
                review_security, self._repo, pr_number, diff,
                task.get("security_constraints", []), self.config
            )
            code_result = code_future.result(timeout=300)
            sec_result = sec_future.result(timeout=300)

        return code_result, sec_result

    def _notify_escalation(self, task_id: str, message: str) -> None:
        esc_dir = self.project_root / ".agentflow" / "escalations"
        esc_dir.mkdir(parents=True, exist_ok=True)
        (esc_dir / f"{task_id}.md").write_text(
            f"# Escalation: {task_id}\n\n{message}\n"
        )

    def _check_approval(self, task_id: str) -> bool:
        approval_file = self.project_root / ".agentflow" / "approvals.json"
        if not approval_file.exists():
            return False
        try:
            approved = json.loads(approval_file.read_text())
            return task_id in approved
        except (json.JSONDecodeError, TypeError):
            return False

    def status(self) -> str:
        all_states = self._state.all_tasks()
        merged = sum(1 for s in all_states if s.status == TaskStatus.MERGED)
        total = len(all_states)
        report = self._tracker.report()
        real_k = report.get("real_total", 0) // 1000
        shadow_k = report.get("shadow_total", 0) // 1000

        lines = [
            f"Project: {self.project_root.name}  |  Tasks: {merged}/{total} complete"
            f"  |  Tokens: {real_k}k real / {shadow_k}k shadow",
            "",
            f"{'TASK_ID':<12} {'STATUS':<25} {'TOKENS':<10} {'PR'}",
        ]
        for s in all_states:
            tok = f"{s.tokens_consumed // 1000}k" if s.tokens_consumed else "—"
            pr = f"#{s.pr_number}" if s.pr_number else "—"
            lines.append(f"{s.task_id:<12} {s.status.value:<25} {tok:<10} {pr}")

        return "\n".join(lines)
