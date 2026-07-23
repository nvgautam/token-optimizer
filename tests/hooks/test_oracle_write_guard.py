"""Unit tests for oracle_write_guard.py hook."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project structure with .agentflow directory."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    agentflow_dir = project_root / ".agentflow"
    agentflow_dir.mkdir()
    return project_root, agentflow_dir


@pytest.fixture
def oracle_state_file(temp_project):
    """Create a session state file with session_type='oracle'."""
    project_root, agentflow_dir = temp_project
    sessions_dir = agentflow_dir / "sessions" / "test-sid"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    state_file = sessions_dir / "session_state.json"
    state_file.write_text(json.dumps({"session_type": "oracle"}))
    os.environ["AGENTFLOW_SESSION_ID"] = "test-sid"
    yield project_root, agentflow_dir, state_file
    if "AGENTFLOW_SESSION_ID" in os.environ:
        del os.environ["AGENTFLOW_SESSION_ID"]


def test_oracle_write_allowed_file(oracle_state_file, monkeypatch):
    """Oracle session writing to allowed file (design_status.md) succeeds."""
    project_root, agentflow_dir, _ = oracle_state_file

    # Create design_status.md (default allowed file)
    allowed_file = project_root / "design_status.md"
    allowed_file.write_text("# Design Status")

    # Change to project root
    monkeypatch.chdir(project_root)

    # Simulate hook call for Write to allowed file
    hook_input = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(allowed_file)},
    }

    hook_script = Path(__file__).parent.parent.parent / "agentflow" / "hooks" / "oracle_write_guard.py"
    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )

    assert result.returncode == 0, f"Hook should allow write to {allowed_file}. stderr: {result.stderr}"


def test_oracle_write_blocked_source_file(oracle_state_file, monkeypatch):
    """Oracle session writing to source file (agentflow/init.py) is blocked."""
    project_root, agentflow_dir, _ = oracle_state_file

    # Create agentflow source file
    source_file = project_root / "agentflow" / "init.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("# source code")

    # Change to project root
    monkeypatch.chdir(project_root)

    # Simulate hook call for Write to source file
    hook_input = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(source_file)},
    }

    hook_script = Path(__file__).parent.parent.parent / "agentflow" / "hooks" / "oracle_write_guard.py"
    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )

    assert result.returncode == 1, f"Hook should block write to {source_file}. stdout: {result.stdout}"
    assert "risk" in result.stderr.lower() or "risk" in result.stdout.lower(), "Should warn about risk"


def test_orchestrator_write_succeeds(temp_project, monkeypatch):
    """Orchestrator session writing to any file succeeds."""
    project_root, agentflow_dir = temp_project

    # Create orchestrator session state
    sessions_dir = agentflow_dir / "sessions" / "orchestrator-sid"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    state_file = sessions_dir / "session_state.json"
    state_file.write_text(json.dumps({"session_type": "orchestrator"}))
    os.environ["AGENTFLOW_SESSION_ID"] = "orchestrator-sid"

    # Create a source file
    source_file = project_root / "agentflow" / "init.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("# source code")

    # Change to project root
    monkeypatch.chdir(project_root)

    # Simulate hook call for Write to source file
    hook_input = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(source_file)},
    }

    hook_script = Path(__file__).parent.parent.parent / "agentflow" / "hooks" / "oracle_write_guard.py"
    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )

    assert result.returncode == 0, f"Hook should allow write in orchestrator session. stderr: {result.stderr}"

    if "AGENTFLOW_SESSION_ID" in os.environ:
        del os.environ["AGENTFLOW_SESSION_ID"]


def test_no_session_state_succeeds(temp_project, monkeypatch):
    """Write succeeds when no session_state.json exists (non-oracle default)."""
    project_root, agentflow_dir = temp_project

    # Create a source file
    source_file = project_root / "agentflow" / "init.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("# source code")

    # Change to project root
    monkeypatch.chdir(project_root)

    # Simulate hook call for Write to source file (no session state)
    hook_input = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(source_file)},
    }

    hook_script = Path(__file__).parent.parent.parent / "agentflow" / "hooks" / "oracle_write_guard.py"
    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )

    assert result.returncode == 0, f"Hook should allow write when no oracle session. stderr: {result.stderr}"


def test_oracle_edit_blocked_source_file(oracle_state_file, monkeypatch):
    """Oracle session editing source file is blocked (Edit tool)."""
    project_root, agentflow_dir, _ = oracle_state_file

    # Create agentflow source file
    source_file = project_root / "agentflow" / "init.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("# source code")

    # Change to project root
    monkeypatch.chdir(project_root)

    # Simulate hook call for Edit to source file
    hook_input = {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(source_file)},
    }

    hook_script = Path(__file__).parent.parent.parent / "agentflow" / "hooks" / "oracle_write_guard.py"
    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )

    assert result.returncode == 1, f"Hook should block edit to {source_file}. stdout: {result.stdout}"


def test_custom_allowlist(oracle_state_file, monkeypatch):
    """Oracle session with custom allowlist allows specified files."""
    project_root, agentflow_dir, _ = oracle_state_file

    # Create custom allowlist
    allowlist_file = agentflow_dir / "oracle_allowlist.json"
    custom_file = project_root / "custom_config.yaml"
    allowlist_file.write_text(json.dumps([
        "design_status.md",
        "custom_config.yaml",
    ]))
    custom_file.write_text("config: value")

    # Change to project root
    monkeypatch.chdir(project_root)

    # Simulate hook call for Write to custom allowed file
    hook_input = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(custom_file)},
    }

    hook_script = Path(__file__).parent.parent.parent / "agentflow" / "hooks" / "oracle_write_guard.py"
    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )

    assert result.returncode == 0, f"Hook should allow write to custom allowlist file. stderr: {result.stderr}"


def test_invalid_json_input(oracle_state_file, monkeypatch):
    """Hook gracefully handles invalid JSON input."""
    project_root, agentflow_dir, _ = oracle_state_file

    # Change to project root
    monkeypatch.chdir(project_root)

    hook_script = Path(__file__).parent.parent.parent / "agentflow" / "hooks" / "oracle_write_guard.py"
    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input="invalid json {",
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )

    assert result.returncode == 0, "Hook should exit 0 on invalid JSON (fail-open)"


def test_missing_file_path_in_input(oracle_state_file, monkeypatch):
    """Hook exits 0 when file_path is not in tool_input."""
    project_root, agentflow_dir, _ = oracle_state_file

    # Change to project root
    monkeypatch.chdir(project_root)

    hook_input = {
        "tool_name": "Write",
        "tool_input": {},
    }

    hook_script = Path(__file__).parent.parent.parent / "agentflow" / "hooks" / "oracle_write_guard.py"
    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )

    assert result.returncode == 0, "Hook should exit 0 when file_path is missing"


def test_default_allowlist_files(oracle_state_file, monkeypatch):
    """Default allowlist includes design_status.md, architecture.md, execution_plan.md, tasks.json."""
    project_root, agentflow_dir, _ = oracle_state_file

    allowed_files = [
        "design_status.md",
        "architecture.md",
        "execution_plan.md",
        "tasks.json",
    ]

    for filename in allowed_files:
        file_path = project_root / filename
        file_path.write_text(f"# {filename}")

        # Change to project root
        monkeypatch.chdir(project_root)

        hook_input = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(file_path)},
        }

        hook_script = Path(__file__).parent.parent.parent / "agentflow" / "hooks" / "oracle_write_guard.py"
        result = subprocess.run(
            [sys.executable, str(hook_script)],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            cwd=str(project_root),
        )

        assert result.returncode == 0, f"Hook should allow write to {filename}. stderr: {result.stderr}"
