import json
import pytest
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from agentflow.hooks.post_tool_use import validate_state_files

def test_tasks_json_validation_passes(tmp_path):
    tasks_path = tmp_path / "tasks.json"
    tasks_data = {
        "tasks": [
            {"task_id": "T-001", "status": "pending"},
            {"task_id": "T-002", "status": "complete"}
        ]
    }
    tasks_path.write_text(json.dumps(tasks_data), encoding="utf-8")
    
    # execution_plan.md doesn't exist, so validation passes.
    validate_state_files(tmp_path)

def test_tasks_json_validation_fails_extra_keys(tmp_path, capsys):
    tasks_path = tmp_path / "tasks.json"
    tasks_data = {
        "tasks": [
            {"task_id": "T-001", "status": "pending", "description": "some description"}
        ]
    }
    tasks_path.write_text(json.dumps(tasks_data), encoding="utf-8")
    
    with pytest.raises(SystemExit) as exc:
        validate_state_files(tmp_path)
    
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "contains extra keys not allowed" in captured.err

def test_addendum_validation_passes(tmp_path):
    ep_path = tmp_path / "execution_plan.md"
    ep_content = """
## Addendum: T-321 — Some Title
**Goal:** Do something.
**Files:**
- `file.py`
**Test scenarios:**
- scenario 1
**OWNS:** `file.py`
**estimated_lines:** 50
"""
    ep_path.write_text(ep_content, encoding="utf-8")
    
    # Mock subprocess.run for git diff
    mock_run = MagicMock()
    mock_run.returncode = 0
    mock_run.stdout = "+## Addendum: T-321 — Some Title\n"
    
    with patch("subprocess.run", return_value=mock_run):
        validate_state_files(tmp_path)

def test_addendum_validation_fails_missing_field(tmp_path, capsys):
    ep_path = tmp_path / "execution_plan.md"
    ep_content = """
## Addendum: T-321 — Some Title
**Goal:** Do something.
**Files:**
- `file.py`
**Test scenarios:**
- scenario 1
**estimated_lines:** 50
"""  # Missing **OWNS:**
    ep_path.write_text(ep_content, encoding="utf-8")
    
    # Mock subprocess.run for git diff
    mock_run = MagicMock()
    mock_run.returncode = 0
    mock_run.stdout = "+## Addendum: T-321 — Some Title\n"
    
    with patch("subprocess.run", return_value=mock_run):
        with pytest.raises(SystemExit) as exc:
            validate_state_files(tmp_path)
            
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "missing required field: **OWNS:**" in captured.err
