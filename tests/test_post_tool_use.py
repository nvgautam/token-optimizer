"""Tests for agentflow/hooks/post_tool_use.py"""
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


def _make_transcript(tmp_path: Path, entries: list[dict]) -> Path:
    t = tmp_path / "transcript.jsonl"
    t.write_text("\n".join(json.dumps(e) for e in entries))
    return t


# --- compute_fill ---

def test_compute_fill_sums_input_fields():
    from agentflow.hooks.post_tool_use import compute_fill
    usage = {
        "input_tokens": 100,
        "cache_read_input_tokens": 50,
        "cache_creation_input_tokens": 25,
        "output_tokens": 999,  # should be ignored
    }
    assert compute_fill(usage) == 175


def test_compute_fill_missing_fields():
    from agentflow.hooks.post_tool_use import compute_fill
    assert compute_fill({}) == 0


# --- extract_fill_from_transcript ---

def test_extract_fill_from_transcript_last_usage(tmp_path):
    from agentflow.hooks.post_tool_use import extract_fill_from_transcript
    transcript = _make_transcript(tmp_path, [
        {"type": "assistant", "message": {"usage": {"input_tokens": 100, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}},
        {"type": "user", "message": {}},
        {"type": "assistant", "message": {"usage": {"input_tokens": 200, "cache_read_input_tokens": 10, "cache_creation_input_tokens": 5}}},
    ])
    assert extract_fill_from_transcript(str(transcript)) == 215


def test_extract_fill_from_transcript_absent_transcript():
    from agentflow.hooks.post_tool_use import extract_fill_from_transcript
    assert extract_fill_from_transcript("/nonexistent/path.jsonl") is None


def test_extract_fill_from_transcript_no_assistant_entries(tmp_path):
    from agentflow.hooks.post_tool_use import extract_fill_from_transcript
    transcript = _make_transcript(tmp_path, [
        {"type": "user", "message": {"content": "hello"}},
    ])
    assert extract_fill_from_transcript(str(transcript)) is None


def test_extract_fill_from_transcript_skips_malformed_lines(tmp_path):
    from agentflow.hooks.post_tool_use import extract_fill_from_transcript
    t = tmp_path / "transcript.jsonl"
    t.write_text('not json\n{"type":"assistant","message":{"usage":{"input_tokens":42}}}\n')
    assert extract_fill_from_transcript(str(t)) == 42


# --- main() happy path ---

def test_main_writes_context_fill_json(tmp_path):
    transcript = _make_transcript(tmp_path, [
        {"type": "assistant", "message": {"usage": {"input_tokens": 300, "cache_read_input_tokens": 50, "cache_creation_input_tokens": 0}}},
    ])
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    payload = json.dumps({"transcript_path": str(transcript)})

    code = _invoke(payload, env={
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "AGENTFLOW_SESSION_ID": "",
    })

    assert code == 0
    fill_path = agentflow_dir / "context_fill.json"
    assert fill_path.exists()
    data = json.loads(fill_path.read_text())
    assert data["fill_tokens"] == 350
    assert "ts" in data


def test_main_absent_transcript_exits_clean(tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    payload = json.dumps({"transcript_path": "/nonexistent/path.jsonl"})

    code = _invoke(payload, env={
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "AGENTFLOW_SESSION_ID": "",
    })

    assert code == 0
    assert not (agentflow_dir / "context_fill.json").exists()


def test_main_malformed_json_payload_exits_zero(tmp_path):
    code = _invoke("not valid json", env={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert code == 0


# --- sync_tasks_in_flight ---

def test_sync_tasks_in_flight_writes_on_current_round_write(tmp_path, monkeypatch):
    from agentflow.hooks.post_tool_use import sync_tasks_in_flight
    af = tmp_path / ".agentflow"
    af.mkdir()
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
    content = json.dumps({"round_id": "r1", "task_ids": ["T-001", "T-002"]})
    sync_tasks_in_flight("Write", {"file_path": str(tmp_path / ".agentflow/current_round.json"), "content": content}, af)
    tif = af / "tasks_in_flight.json"
    assert tif.exists()
    assert json.loads(tif.read_text()) == ["T-001", "T-002"]


def test_sync_tasks_in_flight_noop_for_non_write_tool(tmp_path):
    from agentflow.hooks.post_tool_use import sync_tasks_in_flight
    af = tmp_path / ".agentflow"
    af.mkdir()
    content = json.dumps({"round_id": "r1", "task_ids": ["T-001"]})
    sync_tasks_in_flight("Edit", {"file_path": str(tmp_path / ".agentflow/current_round.json"), "content": content}, af)
    assert not (af / "tasks_in_flight.json").exists()


def test_sync_tasks_in_flight_noop_for_other_file(tmp_path):
    from agentflow.hooks.post_tool_use import sync_tasks_in_flight
    af = tmp_path / ".agentflow"
    af.mkdir()
    content = json.dumps({"task_ids": ["T-001"]})
    sync_tasks_in_flight("Write", {"file_path": str(tmp_path / "other.json"), "content": content}, af)
    assert not (af / "tasks_in_flight.json").exists()


def test_sync_tasks_in_flight_noop_for_empty_task_ids(tmp_path):
    from agentflow.hooks.post_tool_use import sync_tasks_in_flight
    af = tmp_path / ".agentflow"
    af.mkdir()
    content = json.dumps({"round_id": "r1", "task_ids": []})
    sync_tasks_in_flight("Write", {"file_path": str(tmp_path / ".agentflow/current_round.json"), "content": content}, af)
    assert not (af / "tasks_in_flight.json").exists()


def test_main_write_is_atomic(tmp_path):
    """context_fill.json should not appear as a partial file mid-write."""
    transcript = _make_transcript(tmp_path, [
        {"type": "assistant", "message": {"usage": {"input_tokens": 100}}},
    ])
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    payload = json.dumps({"transcript_path": str(transcript)})

    code = _invoke(payload, env={
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "AGENTFLOW_SESSION_ID": "",
    })

    assert code == 0
    fill_path = agentflow_dir / "context_fill.json"
    # If atomic, the file is either absent or fully written — never partial
    data = json.loads(fill_path.read_text())
    assert isinstance(data["fill_tokens"], int)


# --- per-SID path tests ---

def test_main_writes_to_sid_path(tmp_path):
    """When AGENTFLOW_SESSION_ID is set, context_fill.json goes to sessions/<SID>/."""
    transcript = _make_transcript(tmp_path, [
        {"type": "assistant", "message": {"usage": {"input_tokens": 300, "cache_read_input_tokens": 50, "cache_creation_input_tokens": 0}}},
    ])
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    payload = json.dumps({"transcript_path": str(transcript)})

    code = _invoke(payload, env={
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "AGENTFLOW_SESSION_ID": "test-session-123",
    })

    assert code == 0
    # Check that file was written to sessions/<SID>/ path
    fill_path = agentflow_dir / "sessions" / "test-session-123" / "context_fill.json"
    assert fill_path.exists(), f"Expected {fill_path} to exist"
    data = json.loads(fill_path.read_text())
    assert data["fill_tokens"] == 350
    assert "ts" in data
    # Ensure root-level file was NOT created
    root_fill_path = agentflow_dir / "context_fill.json"
    assert not root_fill_path.exists(), "Root-level context_fill.json should not exist when SID is set"


def test_main_writes_to_root_path_without_sid(tmp_path):
    """When AGENTFLOW_SESSION_ID is absent, context_fill.json goes to root (backward compat)."""
    transcript = _make_transcript(tmp_path, [
        {"type": "assistant", "message": {"usage": {"input_tokens": 300, "cache_read_input_tokens": 50, "cache_creation_input_tokens": 0}}},
    ])
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    payload = json.dumps({"transcript_path": str(transcript)})

    # Explicitly set AGENTFLOW_SESSION_ID to empty string to override any env setting
    code = _invoke(payload, env={
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "AGENTFLOW_SESSION_ID": "",
    })

    assert code == 0
    fill_path = agentflow_dir / "context_fill.json"
    assert fill_path.exists()
    data = json.loads(fill_path.read_text())
    assert data["fill_tokens"] == 350
    assert "ts" in data


def test_main_writes_to_root_path_with_empty_sid(tmp_path):
    """When AGENTFLOW_SESSION_ID is empty string, context_fill.json goes to root (backward compat)."""
    transcript = _make_transcript(tmp_path, [
        {"type": "assistant", "message": {"usage": {"input_tokens": 300, "cache_read_input_tokens": 50, "cache_creation_input_tokens": 0}}},
    ])
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    payload = json.dumps({"transcript_path": str(transcript)})

    # Explicitly set AGENTFLOW_SESSION_ID to empty string
    code = _invoke(payload, env={
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "AGENTFLOW_SESSION_ID": "",
    })

    assert code == 0
    fill_path = agentflow_dir / "context_fill.json"
    assert fill_path.exists()
    data = json.loads(fill_path.read_text())
    assert data["fill_tokens"] == 350
    assert "ts" in data


# --- sync_tasks_in_flight SID-scoping tests ---

def test_main_sync_tasks_in_flight_sid_scoped(tmp_path):
    """main() should sync tasks_in_flight to SID-scoped path when AGENTFLOW_SESSION_ID is set."""
    transcript = _make_transcript(tmp_path, [
        {"type": "assistant", "message": {"usage": {"input_tokens": 100}}},
    ])
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    payload = json.dumps({
        "transcript_path": str(transcript),
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(tmp_path / ".agentflow/current_round.json"),
            "content": json.dumps({"task_ids": ["T-100", "T-101"]})
        }
    })

    code = _invoke(payload, env={
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "AGENTFLOW_SESSION_ID": "my-session-999",
    })

    assert code == 0
    # Should write to sessions/my-session-999/tasks_in_flight.json
    sid_tif_path = agentflow_dir / "sessions" / "my-session-999" / "tasks_in_flight.json"
    assert sid_tif_path.exists()
    assert json.loads(sid_tif_path.read_text()) == ["T-100", "T-101"]

    # Ensure root-level file was NOT created
    flat_tif = agentflow_dir / "tasks_in_flight.json"
    assert not flat_tif.exists()


# --- detect_pr_merge ---

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
