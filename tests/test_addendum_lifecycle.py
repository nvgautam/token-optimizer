import json
import pytest
from pathlib import Path
import tempfile
import os

from agentflow.hooks.post_tool_use import detect_pr_merge

def test_addendum_lifecycle(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    agentflow_dir = project_root / ".agentflow"
    agentflow_dir.mkdir()
    
    tasks_path = project_root / "tasks.json"
    ep_path = project_root / "execution_plan.md"
    archive_path = agentflow_dir / "addendums_archive.md"
    
    tasks_path.write_text(json.dumps({"tasks": [{"task_id": "T-001", "status": "pending"}]}))
    ep_content = """# Plan
| T-001 | Description | pending |

## Addendum: T-001
This is the addendum for T-001.
It spans multiple lines.

## Next Section
Something else
"""
    ep_path.write_text(ep_content)
    
    # Mock session
    session_file_path = agentflow_dir / "session_state.json"
    session_file_path.write_text(json.dumps({"session_type": "orchestrator"}))
    os.environ["AGENTFLOW_SESSION_ID"] = ""
    
    # Run the hook
    detect_pr_merge("Bash", {}, "✓ Merged pull request feat(T-001)", agentflow_dir, project_root)
    
    # Assertions
    tasks_data = json.loads(tasks_path.read_text())
    assert tasks_data["tasks"][0]["status"] == "complete"
    
    new_ep_content = ep_path.read_text()
    assert "MERGED (auto)" in new_ep_content
    assert "## Addendum: T-001" not in new_ep_content
    assert "## Next Section" in new_ep_content
    
    archive_content = archive_path.read_text()
    assert "## Addendum: T-001" in archive_content
    assert "This is the addendum for T-001." in archive_content
    
    # Idempotent check
    detect_pr_merge("Bash", {}, "✓ Merged pull request feat(T-001)", agentflow_dir, project_root)
    archive_content2 = archive_path.read_text()
    assert archive_content == archive_content2

