import json
from pathlib import Path
import pytest
from agentflow.tools.cleanup_violations import (
    flatten_archive,
    append_to_archive,
    _split_description,
    auto_file_size_violations,
)


# ============================================================================
# auto_file_size_violations tests
# ============================================================================

def test_auto_file_size_violations_skips_absent_violations(tmp_path):
    """auto_file_size_violations returns early if violations_path absent."""
    project_root = tmp_path
    agentflow_dir = project_root / ".agentflow"
    agentflow_dir.mkdir()

    # No violations file
    tasks_path = project_root / "tasks.json"
    tasks_path.write_text(json.dumps({"tasks": []}))

    # Should not raise
    auto_file_size_violations(project_root)

    # tasks.json should be unchanged
    assert json.loads(tasks_path.read_text())["tasks"] == []


def test_auto_file_size_violations_skips_absent_tasks_json(tmp_path):
    """auto_file_size_violations returns early if tasks.json absent."""
    project_root = tmp_path
    agentflow_dir = project_root / ".agentflow"
    agentflow_dir.mkdir()

    violations_path = agentflow_dir / "size_violations.jsonl"
    violations_path.write_text(json.dumps({"file": "test.py", "limit": 250}) + "\n")

    # No tasks.json
    # Should not raise
    auto_file_size_violations(project_root)


def test_auto_file_size_violations_skips_under_limit(tmp_path):
    """auto_file_size_violations skips files already under limit."""
    project_root = tmp_path
    agentflow_dir = project_root / ".agentflow"
    agentflow_dir.mkdir()

    tasks_path = project_root / "tasks.json"
    tasks_path.write_text(json.dumps({"tasks": []}))

    # File exists but is under limit
    test_file = project_root / "test.py"
    test_file.write_text("\n" * 200)

    violations_path = agentflow_dir / "size_violations.jsonl"
    violations_path.write_text(
        json.dumps({"file": "test.py", "limit": 250, "ts": "2026-07-17T00:00:00"}) + "\n"
    )

    auto_file_size_violations(project_root)

    # No new tasks should be added
    result = json.loads(tasks_path.read_text())
    assert len(result["tasks"]) == 0


def test_auto_file_size_violations_files_new_task(tmp_path):
    """auto_file_size_violations files new task for oversized file."""
    project_root = tmp_path
    agentflow_dir = project_root / ".agentflow"
    agentflow_dir.mkdir()

    tasks_path = project_root / "tasks.json"
    tasks_path.write_text(json.dumps({"tasks": []}))

    # Oversized file
    test_file = project_root / "test.py"
    test_file.write_text("\n" * 260)

    violations_path = agentflow_dir / "size_violations.jsonl"
    violations_path.write_text(
        json.dumps({"file": "test.py", "limit": 250, "ts": "2026-07-17T00:00:00"}) + "\n"
    )

    auto_file_size_violations(project_root)

    result = json.loads(tasks_path.read_text())
    assert len(result["tasks"]) == 1

    task = result["tasks"][0]
    assert task["task_id"] == "T-001"
    assert task["title"] == "Split test.py — size violation"
    assert task["status"] == "pending"
    assert task["owns"] == ["test.py"]
    assert "2026-07-17T00:00:00" in task["description"]


def test_auto_file_size_violations_idempotent(tmp_path):
    """auto_file_size_violations is idempotent — same violation only filed once."""
    project_root = tmp_path
    agentflow_dir = project_root / ".agentflow"
    agentflow_dir.mkdir()

    tasks_path = project_root / "tasks.json"
    tasks_path.write_text(json.dumps({"tasks": []}))

    # Oversized file
    test_file = project_root / "test.py"
    test_file.write_text("\n" * 260)

    violations_path = agentflow_dir / "size_violations.jsonl"
    violations_path.write_text(
        json.dumps({"file": "test.py", "limit": 250, "ts": "2026-07-17T00:00:00"}) + "\n"
    )

    # First run
    auto_file_size_violations(project_root)
    result1 = json.loads(tasks_path.read_text())
    assert len(result1["tasks"]) == 1

    # Second run with same violation
    auto_file_size_violations(project_root)
    result2 = json.loads(tasks_path.read_text())
    assert len(result2["tasks"]) == 1  # No new task added


def test_auto_file_size_violations_skips_already_filed(tmp_path):
    """auto_file_size_violations skips violations already filed in tasks.json."""
    project_root = tmp_path
    agentflow_dir = project_root / ".agentflow"
    agentflow_dir.mkdir()

    # Pre-existing task for the file
    tasks_path = project_root / "tasks.json"
    existing = {
        "tasks": [
            {
                "task_id": "T-001",
                "title": "Split test.py — size violation",
                "description": "Split test.py (260 lines, limit 250). Violation timestamp: 2026-07-17T00:00:00.",
                "owns": ["test.py"],
                "status": "pending"
            }
        ]
    }
    tasks_path.write_text(json.dumps(existing))

    # Oversized file
    test_file = project_root / "test.py"
    test_file.write_text("\n" * 260)

    violations_path = agentflow_dir / "size_violations.jsonl"
    violations_path.write_text(
        json.dumps({"file": "test.py", "limit": 250, "ts": "2026-07-17T00:00:00"}) + "\n"
    )

    auto_file_size_violations(project_root)

    result = json.loads(tasks_path.read_text())
    assert len(result["tasks"]) == 1  # No new task added


def test_auto_file_size_violations_skips_nonexistent_files(tmp_path):
    """auto_file_size_violations skips violations for nonexistent files."""
    project_root = tmp_path
    agentflow_dir = project_root / ".agentflow"
    agentflow_dir.mkdir()

    tasks_path = project_root / "tasks.json"
    tasks_path.write_text(json.dumps({"tasks": []}))

    # File does NOT exist
    violations_path = agentflow_dir / "size_violations.jsonl"
    violations_path.write_text(
        json.dumps({"file": "nonexistent.py", "limit": 250, "ts": "2026-07-17T00:00:00"}) + "\n"
    )

    auto_file_size_violations(project_root)

    result = json.loads(tasks_path.read_text())
    assert len(result["tasks"]) == 0


def test_auto_file_size_violations_increments_task_id(tmp_path):
    """auto_file_size_violations increments task ID based on existing tasks."""
    project_root = tmp_path
    agentflow_dir = project_root / ".agentflow"
    agentflow_dir.mkdir()

    # Pre-existing tasks
    tasks_path = project_root / "tasks.json"
    existing = {
        "tasks": [
            {"task_id": "T-001", "title": "Task 1", "status": "pending"},
            {"task_id": "T-002", "title": "Task 2", "status": "complete"},
        ]
    }
    tasks_path.write_text(json.dumps(existing))

    # Oversized file
    test_file = project_root / "test.py"
    test_file.write_text("\n" * 260)

    violations_path = agentflow_dir / "size_violations.jsonl"
    violations_path.write_text(
        json.dumps({"file": "test.py", "limit": 250, "ts": "2026-07-17T00:00:00"}) + "\n"
    )

    auto_file_size_violations(project_root)

    result = json.loads(tasks_path.read_text())
    assert len(result["tasks"]) == 3
    new_task = next(t for t in result["tasks"] if t["task_id"] == "T-003")
    assert new_task["title"] == "Split test.py — size violation"


def test_auto_file_size_violations_handles_archive(tmp_path):
    """auto_file_size_violations considers archived tasks to avoid re-filing."""
    project_root = tmp_path
    agentflow_dir = project_root / ".agentflow"
    agentflow_dir.mkdir()

    tasks_path = project_root / "tasks.json"
    tasks_path.write_text(json.dumps({"tasks": []}))

    archive_path = agentflow_dir / "tasks.archive.json"
    archived = [
        {
            "task_id": "T-001",
            "title": "Split archived.py — size violation",
            "description": "Split archived.py. Violation timestamp: 2026-07-17T00:00:00.",
            "owns": ["archived.py"],
            "status": "complete"
        }
    ]
    archive_path.write_text(json.dumps(archived))

    # File still oversized
    test_file = project_root / "archived.py"
    test_file.write_text("\n" * 260)

    violations_path = agentflow_dir / "size_violations.jsonl"
    violations_path.write_text(
        json.dumps({"file": "archived.py", "limit": 250, "ts": "2026-07-17T00:00:00"}) + "\n"
    )

    auto_file_size_violations(project_root)

    result = json.loads(tasks_path.read_text())
    # Should not file a new task because it's already in archive
    assert len(result["tasks"]) == 0


def test_auto_file_size_violations_malformed_violations(tmp_path):
    """auto_file_size_violations handles malformed lines in violations_path."""
    project_root = tmp_path
    agentflow_dir = project_root / ".agentflow"
    agentflow_dir.mkdir()

    tasks_path = project_root / "tasks.json"
    tasks_path.write_text(json.dumps({"tasks": []}))

    test_file = project_root / "test.py"
    test_file.write_text("\n" * 260)

    violations_path = agentflow_dir / "size_violations.jsonl"
    violations_path.write_text(
        "not json\n" +
        json.dumps({"file": "test.py", "limit": 250, "ts": "2026-07-17T00:00:00"}) + "\n" +
        "also not json\n"
    )

    # Should not raise
    auto_file_size_violations(project_root)

    result = json.loads(tasks_path.read_text())
    # Should have filed the valid violation
    assert len(result["tasks"]) == 1
