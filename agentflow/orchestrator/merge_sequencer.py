"""Post-approval merge sequencer: merges worktree branches in DAG topological order."""

from __future__ import annotations

import subprocess
from pathlib import Path

from agentflow.config.schema import AgentFlowConfig
from agentflow.orchestrator.state import ProjectState, TaskStatus
from agentflow.tools.git import GitError, delete_worktree


class MergeSequencer:
    def __init__(self, project_root: Path, config: AgentFlowConfig, state: ProjectState):
        self._project_root = project_root
        self._config = config
        self._state = state

    def merge_task(self, task_id: str, dag) -> bool:
        """Merge the worktree branch for task_id into main.

        Returns True on success, False on conflict or git error.
        Deletes worktree and transitions state to MERGED on success.
        """
        worktree_path = self._project_root / "workspaces" / task_id
        branch = f"task/{task_id}"

        try:
            subprocess.run(
                ["git", "merge", "--no-ff", branch, "-m", f"Merge task {task_id}"],
                cwd=self._project_root,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode() if exc.stderr else ""
            # abort merge on conflict
            subprocess.run(
                ["git", "merge", "--abort"],
                cwd=self._project_root,
                capture_output=True,
            )
            return False
        except Exception:
            return False

        try:
            delete_worktree(worktree_path)
        except (GitError, Exception):
            pass  # worktree cleanup is best-effort

        try:
            self._state.transition(task_id, TaskStatus.MERGED)
        except Exception:
            pass

        return True

    def merge_all_approved(self, dag, state: ProjectState) -> list[str]:
        """Merge all HUMAN_APPROVED tasks in topological order.

        Returns list of successfully merged task_ids.
        """
        order = dag.topological_order()
        merged: list[str] = []

        for task_id in order:
            try:
                ts = state.get(task_id)
            except KeyError:
                continue
            if ts.status != TaskStatus.HUMAN_APPROVED:
                continue
            if self.merge_task(task_id, dag):
                merged.append(task_id)

        return merged
