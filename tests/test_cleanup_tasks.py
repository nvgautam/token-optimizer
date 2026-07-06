import json
from agentflow.tools.cleanup_tasks import cleanup, auto_file_size_violations

def test_auto_file_size_violations(tmp_path):
    # Setup paths
    project_root = tmp_path
    agentflow_dir = project_root / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    tasks_path = project_root / "tasks.json"
    archive_path = agentflow_dir / "tasks.archive.json"
    violations_path = agentflow_dir / "size_violations.jsonl"

    # 1. Create a tasks.json with some existing tasks
    initial_tasks = {
        "project": "test",
        "version": "1.0.0",
        "tasks": [
            {
                "task_id": "T-001",
                "title": "Task 1",
                "description": "Some description",
                "status": "complete"
            },
            {
                "task_id": "T-002",
                "title": "Already filed violation",
                "description": "Split path/to/already_filed.py to resolve size violation. Violation timestamp: 2026-07-06T00:00:00.000000.",
                "owns": ["path/to/already_filed.py"],
                "status": "pending"
            }
        ]
    }
    with open(tasks_path, "w", encoding="utf-8") as f:
        json.dump(initial_tasks, f, indent=2)

    # 2. Create tasks.archive.json with an archived task
    archived_tasks = [
        {
            "task_id": "T-003",
            "title": "Archived violation",
            "description": "Split path/to/archived_filed.py to resolve size violation. Violation timestamp: 2026-07-06T11:11:11.111111.",
            "owns": ["path/to/archived_filed.py"],
            "status": "complete"
        }
    ]
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(archived_tasks, f, indent=2)

    # 3. Create dummy source files
    # Oversized file 1 (limit 250, actual 260) - should be filed (T-004)
    oversized_file_1 = project_root / "path" / "to" / "oversized1.py"
    oversized_file_1.parent.mkdir(parents=True, exist_ok=True)
    oversized_file_1.write_text("\n" * 260, encoding="utf-8")

    # Resolved file (limit 250, actual 200) - should be ignored
    resolved_file = project_root / "path" / "to" / "resolved.py"
    resolved_file.parent.mkdir(parents=True, exist_ok=True)
    resolved_file.write_text("\n" * 200, encoding="utf-8")

    # Already filed file (limit 250, actual 260) - should be ignored (deduped)
    already_filed_file = project_root / "path" / "to" / "already_filed.py"
    already_filed_file.parent.mkdir(parents=True, exist_ok=True)
    already_filed_file.write_text("\n" * 260, encoding="utf-8")

    # Archived filed file (limit 250, actual 260) - should be ignored (deduped)
    archived_filed_file = project_root / "path" / "to" / "archived_filed.py"
    archived_filed_file.parent.mkdir(parents=True, exist_ok=True)
    archived_filed_file.write_text("\n" * 260, encoding="utf-8")

    # Non-existent file - should be ignored
    # path/to/nonexistent.py does not exist on disk

    # 4. Create size_violations.jsonl
    violations = [
        # Should be filed (new)
        {"file": "path/to/oversized1.py", "blocked_lines": 260, "actual_lines": 260, "limit": 250, "ts": "2026-07-06T12:00:00.000000"},
        # Should be ignored (resolved line count)
        {"file": "path/to/resolved.py", "blocked_lines": 260, "actual_lines": 260, "limit": 250, "ts": "2026-07-06T13:00:00.000000"},
        # Should be ignored (already filed in tasks.json)
        {"file": "path/to/already_filed.py", "blocked_lines": 260, "actual_lines": 260, "limit": 250, "ts": "2026-07-06T00:00:00.000000"},
        # Should be ignored (already filed in archive)
        {"file": "path/to/archived_filed.py", "blocked_lines": 260, "actual_lines": 260, "limit": 250, "ts": "2026-07-06T11:11:11.111111"},
        # Should be ignored (non-existent file)
        {"file": "path/to/nonexistent.py", "blocked_lines": 260, "actual_lines": 260, "limit": 250, "ts": "2026-07-06T14:00:00.000000"},
    ]
    with open(violations_path, "w", encoding="utf-8") as f:
        for v in violations:
            f.write(json.dumps(v) + "\n")

    # 5. Run auto-filing logic
    auto_file_size_violations(project_root)

    # 6. Verify tasks.json
    with open(tasks_path, "r", encoding="utf-8") as f:
        result = json.load(f)

    tasks = result["tasks"]
    assert len(tasks) == 3  # Initial 2 + 1 new filed task

    # Find the new filed task
    new_task = next((t for t in tasks if t["task_id"] == "T-004"), None)
    assert new_task is not None
    assert new_task["title"] == "Split path/to/oversized1.py — size violation"
    assert "2026-07-06T12:00:00.000000" in new_task["description"]
    assert "limit: 250" in new_task["description"]
    assert new_task["owns"] == ["path/to/oversized1.py"]
    assert new_task["status"] == "pending"

def test_cleanup_triggers_auto_file(tmp_path):
    project_root = tmp_path
    agentflow_dir = project_root / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    tasks_path = project_root / "tasks.json"
    violations_path = agentflow_dir / "size_violations.jsonl"

    initial_tasks = {
        "project": "test",
        "version": "1.0.0",
        "tasks": [
            {
                "task_id": "T-001",
                "title": "Task 1",
                "description": "Some description",
                "status": "complete"
            }
        ]
    }
    with open(tasks_path, "w", encoding="utf-8") as f:
        json.dump(initial_tasks, f, indent=2)

    # Create oversized file
    oversized_file = project_root / "oversized.py"
    oversized_file.write_text("\n" * 300, encoding="utf-8")

    # Create violation
    v = {"file": "oversized.py", "blocked_lines": 300, "actual_lines": 300, "limit": 250, "ts": "2026-07-06T15:00:00"}
    with open(violations_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(v) + "\n")

    # Run cleanup, which should trigger auto_file_size_violations
    cleanup(project_root)

    # Verify task was added and T-001 was trimmed to stub
    with open(tasks_path, "r", encoding="utf-8") as f:
        result = json.load(f)

    tasks = result["tasks"]
    assert len(tasks) == 2

    t1 = next(t for t in tasks if t["task_id"] == "T-001")
    assert len(t1) == 2  # Trimmed to just task_id and status
    assert t1["status"] == "complete"

    t2 = next(t for t in tasks if t["task_id"] == "T-002")
    assert t2["title"] == "Split oversized.py — size violation"
    assert t2["status"] == "pending"
