"""Tests for PR merge detection in agentflow/hooks/post_tool_use.py"""
from __future__ import annotations
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest


def _invoke(stdin_data: str, env: dict | None = None) -> int:
    """Run post_tool_use.main() with given stdin, return exit code."""
    import agentflow.hooks.post_tool_use as mod
    import io

    with patch("sys.stdin", io.StringIO(stdin_data)):
        if env is not None:
            with patch.dict(os.environ, env, clear=False):
                try:
                    mod.main()
                    return 0
                except SystemExit as e:
                    return int(e.code) if e.code is not None else 0
        else:
            try:
                mod.main()
                return 0
            except SystemExit as e:
                return int(e.code) if e.code is not None else 0


def test_detect_pr_merge_fires_on_merged_output(tmp_path):
    """Bash tool output with ✓ Merged pull request and session_type=orchestrate updates tasks/plan."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    sessions_dir = agentflow_dir / "sessions" / "test-session"
    sessions_dir.mkdir(parents=True)
    sessions_dir.joinpath("session_state.json").write_text('{"session_type": "orchestrate"}')

    # Create initial tasks.json
    tasks_json = tmp_path / "tasks.json"
    tasks_json.write_text(json.dumps({
        "project": "agentflow",
        "tasks": [
            {"task_id": "T-229", "status": "pending"}
        ]
    }))

    # Create initial execution_plan.md with Addendum section
    exec_plan = tmp_path / "execution_plan.md"
    exec_plan.write_text("""# Plan

## Milestone 1
| Task | Status |
|---|---|
| T-229 | pending |

## Addendum: T-229
Test addendum for task T-229.
""")

    payload = json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "gh pr merge 42"},
        "tool_response": {
            "output": "✓ Merged pull request #42 (feat(T-229): extend feature X)\n"
        }
    })

    code = _invoke(payload, env={
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "AGENTFLOW_SESSION_ID": "test-session",
    })

    assert code == 0
    # Verify tasks.json updated
    tasks = json.loads(tasks_json.read_text())
    t229 = next((t for t in tasks["tasks"] if t["task_id"] == "T-229"), None)
    assert t229 is not None
    assert t229["status"] == "complete"
    # Verify execution_plan.md marked as MERGED
    plan_text = exec_plan.read_text()
    assert "MERGED" in plan_text


def test_detect_pr_merge_skips_non_orchestrate_session(tmp_path):
    """session_type != orchestrate → no file changes."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    sessions_dir = agentflow_dir / "sessions" / "test-session"
    sessions_dir.mkdir(parents=True)
    sessions_dir.joinpath("session_state.json").write_text('{"session_type": "oracle"}')

    tasks_json = tmp_path / "tasks.json"
    original = json.dumps({"tasks": [{"task_id": "T-229", "status": "pending"}]})
    tasks_json.write_text(original)

    payload = json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "gh pr merge 42"},
        "tool_response": {"output": "✓ Merged pull request #42 (feat(T-229): ...)\n"}
    })

    code = _invoke(payload, env={
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "AGENTFLOW_SESSION_ID": "test-session",
    })

    assert code == 0
    # tasks.json should remain unchanged
    assert tasks_json.read_text() == original


def test_detect_pr_merge_skips_non_bash_tool(tmp_path):
    """tool_name != Bash → no action."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    sessions_dir = agentflow_dir / "sessions" / "test-session"
    sessions_dir.mkdir(parents=True)
    sessions_dir.joinpath("session_state.json").write_text('{"session_type": "orchestrate"}')

    tasks_json = tmp_path / "tasks.json"
    original = json.dumps({"tasks": [{"task_id": "T-229", "status": "pending"}]})
    tasks_json.write_text(original)

    payload = json.dumps({
        "tool_name": "Write",
        "tool_input": {"file_path": "something.md", "content": "text"},
        "tool_response": {"output": "✓ Merged pull request #42 (feat(T-229): ...)\n"}
    })

    code = _invoke(payload, env={
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "AGENTFLOW_SESSION_ID": "test-session",
    })

    assert code == 0
    assert tasks_json.read_text() == original


def test_detect_pr_merge_skips_no_merge_marker(tmp_path):
    """Bash output without ✓ Merged pull request → no action."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    sessions_dir = agentflow_dir / "sessions" / "test-session"
    sessions_dir.mkdir(parents=True)
    sessions_dir.joinpath("session_state.json").write_text('{"session_type": "orchestrate"}')

    tasks_json = tmp_path / "tasks.json"
    original = json.dumps({"tasks": [{"task_id": "T-229", "status": "pending"}]})
    tasks_json.write_text(original)

    payload = json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "gh pr merge 42"},
        "tool_response": {"output": "No merge marker here\n"}
    })

    code = _invoke(payload, env={
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "AGENTFLOW_SESSION_ID": "test-session",
    })

    assert code == 0
    assert tasks_json.read_text() == original


def test_detect_pr_merge_no_task_id_in_title(tmp_path):
    """PR title has no T-NNN → no file changes, no crash."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    sessions_dir = agentflow_dir / "sessions" / "test-session"
    sessions_dir.mkdir(parents=True)
    sessions_dir.joinpath("session_state.json").write_text('{"session_type": "orchestrate"}')

    tasks_json = tmp_path / "tasks.json"
    original = json.dumps({"tasks": [{"task_id": "T-229", "status": "pending"}]})
    tasks_json.write_text(original)

    payload = json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "gh pr merge 42"},
        "tool_response": {"output": "✓ Merged pull request #42 (some random title)\n"}
    })

    code = _invoke(payload, env={
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "AGENTFLOW_SESSION_ID": "test-session",
    })

    assert code == 0
    assert tasks_json.read_text() == original


def test_detect_pr_merge_idempotent(tmp_path):
    """Running twice for same task_id → tasks.json still valid, plan not double-marked."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    sessions_dir = agentflow_dir / "sessions" / "test-session"
    sessions_dir.mkdir(parents=True)
    sessions_dir.joinpath("session_state.json").write_text('{"session_type": "orchestrate"}')

    tasks_json = tmp_path / "tasks.json"
    tasks_json.write_text(json.dumps({
        "project": "agentflow",
        "tasks": [{"task_id": "T-229", "status": "pending"}]
    }))

    exec_plan = tmp_path / "execution_plan.md"
    exec_plan.write_text("""# Plan
## Addendum: T-229
Test addendum.
""")

    payload = json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "gh pr merge 42"},
        "tool_response": {"output": "✓ Merged pull request #42 (feat(T-229): ...)\n"}
    })

    # First run
    code1 = _invoke(payload, env={
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "AGENTFLOW_SESSION_ID": "test-session",
    })
    assert code1 == 0
    first_plan = exec_plan.read_text()

    # Second run with same payload
    code2 = _invoke(payload, env={
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "AGENTFLOW_SESSION_ID": "test-session",
    })
    assert code2 == 0
    second_plan = exec_plan.read_text()

    # Verify tasks.json still valid
    tasks = json.loads(tasks_json.read_text())
    assert tasks["tasks"][0]["status"] == "complete"

    # Verify plan not double-marked (count MERGED occurrences)
    assert first_plan.count("MERGED") == second_plan.count("MERGED")


def test_detect_pr_merge_missing_tasks_json(tmp_path):
    """tasks.json absent → handles gracefully, no crash."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    sessions_dir = agentflow_dir / "sessions" / "test-session"
    sessions_dir.mkdir(parents=True)
    sessions_dir.joinpath("session_state.json").write_text('{"session_type": "orchestrate"}')

    # No tasks.json created
    payload = json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "gh pr merge 42"},
        "tool_response": {"output": "✓ Merged pull request #42 (feat(T-229): ...)\n"}
    })

    code = _invoke(payload, env={
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "AGENTFLOW_SESSION_ID": "test-session",
    })

    # Should exit clean, not crash
    assert code == 0


def test_detect_pr_merge_lockfile_created(tmp_path):
    """After run, .agentflow/tasks.json.lock exists."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    sessions_dir = agentflow_dir / "sessions" / "test-session"
    sessions_dir.mkdir(parents=True)
    sessions_dir.joinpath("session_state.json").write_text('{"session_type": "orchestrate"}')

    tasks_json = tmp_path / "tasks.json"
    tasks_json.write_text(json.dumps({
        "project": "agentflow",
        "tasks": [{"task_id": "T-229", "status": "pending"}]
    }))

    exec_plan = tmp_path / "execution_plan.md"
    exec_plan.write_text("## Addendum: T-229\nTest.\n")

    payload = json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "gh pr merge 42"},
        "tool_response": {"output": "✓ Merged pull request #42 (feat(T-229): ...)\n"}
    })

    code = _invoke(payload, env={
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "AGENTFLOW_SESSION_ID": "test-session",
    })

    assert code == 0
    lock_path = agentflow_dir / "tasks.json.lock"
    assert lock_path.exists()


def test_detect_pr_merge_conventional_commit_variants(tmp_path):
    """Test various conventional commit prefixes: fix, chore, refactor."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    sessions_dir = agentflow_dir / "sessions" / "test-session"
    sessions_dir.mkdir(parents=True)
    sessions_dir.joinpath("session_state.json").write_text('{"session_type": "orchestrate"}')

    for prefix, task_id in [("feat", "T-100"), ("fix", "T-101"), ("chore", "T-102"), ("refactor", "T-103")]:
        tasks_json = tmp_path / "tasks.json"
        tasks_json.write_text(json.dumps({
            "project": "agentflow",
            "tasks": [{"task_id": task_id, "status": "pending"}]
        }))

        exec_plan = tmp_path / "execution_plan.md"
        exec_plan.write_text(f"## Addendum: {task_id}\nTest.\n")

        payload = json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr merge 42"},
            "tool_response": {"output": f"✓ Merged pull request #42 ({prefix}({task_id}): description)\n"}
        })

        code = _invoke(payload, env={
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "AGENTFLOW_SESSION_ID": "test-session",
        })

        assert code == 0
        tasks = json.loads(tasks_json.read_text())
        t = next((t for t in tasks["tasks"] if t["task_id"] == task_id), None)
        assert t is not None
        assert t["status"] == "complete", f"Failed for {prefix}({task_id})"
