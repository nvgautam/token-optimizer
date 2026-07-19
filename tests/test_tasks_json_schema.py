import json
import pytest
from pathlib import Path

def test_tasks_json_schema():
    tasks_path = Path(__file__).resolve().parents[1] / "tasks.json"
    
    if not tasks_path.exists():
        pytest.skip("tasks.json does not exist")
        
    try:
        content = tasks_path.read_text(encoding="utf-8")
        data = json.loads(content)
    except json.JSONDecodeError:
        pytest.fail("tasks.json is not valid JSON")

    assert "tasks" in data, "tasks.json missing 'tasks' key"
    assert isinstance(data["tasks"], list), "'tasks' must be a list"

    for idx, task in enumerate(data["tasks"]):
        assert isinstance(task, dict), f"Task at index {idx} is not a dictionary"
        
        # Enforce exactly two keys: task_id and status
        allowed_keys = {"task_id", "status"}
        actual_keys = set(task.keys())
        
        missing_keys = allowed_keys - actual_keys
        extra_keys = actual_keys - allowed_keys
        
        assert not missing_keys, f"Task at index {idx} missing required keys: {missing_keys}"
        assert not extra_keys, f"Task at index {idx} contains extra keys not allowed: {extra_keys}"
        
        assert isinstance(task["task_id"], str), f"Task {idx} task_id must be a string"
        assert isinstance(task["status"], str), f"Task {idx} status must be a string"
        assert task["status"] in {"pending", "complete", "cancelled"}, f"Task {idx} status invalid"
