"""Tests for T-244: Remove EnterWorktree dependency from worker skill."""

import pytest
from pathlib import Path


@pytest.fixture
def worker_system():
    """Load commands/claude/worker/system.md."""
    path = Path(__file__).parent.parent.parent / "commands" / "claude" / "worker" / "system.md"
    return path.read_text()


@pytest.fixture
def orchestrate_md():
    """Load commands/claude/orchestrate.md."""
    path = Path(__file__).parent.parent.parent / "commands" / "claude" / "orchestrate.md"
    return path.read_text()


class TestWorkerSystemMd:
    """system.md must prohibit EnterWorktree and instruct use of worktree_abs_path."""

    def test_prohibits_enterworktree(self, worker_system):
        """system.md must contain 'EnterWorktree' with prohibition (never/do not)."""
        assert "EnterWorktree" in worker_system, "system.md must mention EnterWorktree"
        # Must contain prohibition language near the mention
        lower = worker_system.lower()
        assert "never" in lower or "do not" in lower or "must not" in lower, \
            "system.md must prohibit EnterWorktree with 'never', 'do not', or 'must not'"

    def test_instructs_worktree_abs_path(self, worker_system):
        """system.md must instruct workers to use worktree_abs_path from context bundle."""
        assert "worktree_abs_path" in worker_system, \
            "system.md must mention worktree_abs_path"
        assert "context bundle" in worker_system.lower(), \
            "system.md must reference context bundle when discussing worktree_abs_path"


class TestOrchestrateMd:
    """orchestrate.md must capture worktree path and pass it to workers."""

    def test_captures_worktree_path(self, orchestrate_md):
        """orchestrate.md must run 'git worktree list | grep <branch> | awk' to capture path."""
        assert "git worktree list" in orchestrate_md and "awk" in orchestrate_md, \
            "orchestrate.md must include 'git worktree list | grep <branch> | awk' to capture path"

    def test_no_old_enterworktree_instruction(self, orchestrate_md):
        """orchestrate.md must NOT contain the old instruction about worker calling EnterWorktree."""
        # The old pattern was: "worker calls `EnterWorktree(path=.claude/worktrees/<branch>)` as its first step"
        assert "worker calls `EnterWorktree" not in orchestrate_md, \
            "orchestrate.md must NOT contain old instruction 'worker calls `EnterWorktree'"

    def test_passes_worktree_abs_path_in_context_bundle(self, orchestrate_md):
        """orchestrate.md must include worktree_abs_path in context bundle instructions."""
        assert "worktree_abs_path" in orchestrate_md, \
            "orchestrate.md must mention worktree_abs_path in context bundle"
        # The context bundle building section should mention it
        assert "context bundle" in orchestrate_md.lower() and "worktree_abs_path" in orchestrate_md, \
            "orchestrate.md must explain that worktree_abs_path goes into context bundle"
