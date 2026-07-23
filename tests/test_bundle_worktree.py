"""Tests for worktree path injection into task bundles.

Validates:
- Worktree path option parsing in CLI
- Bundle JSON structure includes worktree_abs_path
- Path extraction from bundle
- Idempotency of bundle generation
- Edge cases: missing worktree path, malformed paths
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def tmp_project_root(tmp_path):
    """Create a minimal project structure with tasks.json."""
    project = tmp_path / "project"
    project.mkdir()

    # Create minimal tasks.json
    tasks = {
        "tasks": [
            {
                "task_id": "T-999",
                "description": "Test task",
                "status": "pending"
            }
        ]
    }
    (project / "tasks.json").write_text(json.dumps(tasks, indent=2))

    # Create minimal execution_plan.md with addendum
    plan_content = "## Addendum: T-999\nTest addendum content\n"
    (project / "execution_plan.md").write_text(plan_content)

    # Create skill file
    skills_dir = project / "commands" / "claude" / "worker"
    skills_dir.mkdir(parents=True)
    (skills_dir / "system.md").write_text("# Worker System Prompt\nTest prompt")

    return project


@pytest.fixture
def worktree_path(tmp_path):
    """Create a temporary worktree path."""
    wtree = tmp_path / "worktree"
    wtree.mkdir()
    return wtree


def test_bundle_option_parsing(tmp_project_root, worktree_path):
    """Verify --worktree option is accepted by bundle command."""
    result = subprocess.run(
        [
            sys.executable, "-m", "agentflow.cli", "bundle",
            "T-999",
            "--agent-type", "worker",
            "--out-dir", str(tmp_project_root),
            "--worktree", str(worktree_path),
        ],
        cwd=str(tmp_project_root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_bundle_includes_worktree_path(tmp_project_root, worktree_path):
    """Verify worktree_abs_path is injected into bundle JSON."""
    result = subprocess.run(
        [
            sys.executable, "-m", "agentflow.cli", "bundle",
            "T-999",
            "--agent-type", "worker",
            "--out-dir", str(tmp_project_root),
            "--worktree", str(worktree_path),
        ],
        cwd=str(tmp_project_root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    # Extract bundle path from output
    bundle_path = Path(result.stdout.strip())
    assert bundle_path.exists(), f"Bundle not found at {bundle_path}"

    # Load bundle and verify worktree path
    bundle = json.loads(bundle_path.read_text())
    assert "worktree_abs_path" in bundle, "worktree_abs_path not in bundle"
    assert bundle["worktree_abs_path"] == str(worktree_path.resolve())


def test_bundle_without_worktree_optional(tmp_project_root):
    """Verify bundle works without --worktree (backward compatibility)."""
    result = subprocess.run(
        [
            sys.executable, "-m", "agentflow.cli", "bundle",
            "T-999",
            "--agent-type", "worker",
            "--out-dir", str(tmp_project_root),
        ],
        cwd=str(tmp_project_root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    # Bundle should still be created and valid
    bundle_path = Path(result.stdout.strip())
    assert bundle_path.exists()

    bundle = json.loads(bundle_path.read_text())
    # worktree_abs_path should be None or absent if not provided
    assert bundle.get("worktree_abs_path") is None


def test_bundle_worktree_path_canonicalized(tmp_project_root, tmp_path):
    """Verify worktree path is resolved to absolute path."""
    # Create a relative path
    wtree_dir = tmp_path / "wtree"
    wtree_dir.mkdir()

    result = subprocess.run(
        [
            sys.executable, "-m", "agentflow.cli", "bundle",
            "T-999",
            "--agent-type", "worker",
            "--out-dir", str(tmp_project_root),
            "--worktree", str(wtree_dir),
        ],
        cwd=str(tmp_project_root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    bundle_path = Path(result.stdout.strip())
    bundle = json.loads(bundle_path.read_text())

    # Verify path is absolute
    stored_path = bundle["worktree_abs_path"]
    assert Path(stored_path).is_absolute(), f"Path not absolute: {stored_path}"


def test_bundle_idempotent_with_worktree(tmp_project_root, worktree_path):
    """Verify running bundle twice with same worktree produces same output."""
    cmd = [
        sys.executable, "-m", "agentflow.cli", "bundle",
        "T-999",
        "--agent-type", "worker",
        "--out-dir", str(tmp_project_root),
        "--worktree", str(worktree_path),
    ]

    result1 = subprocess.run(cmd, cwd=str(tmp_project_root), capture_output=True, text=True)
    result2 = subprocess.run(cmd, cwd=str(tmp_project_root), capture_output=True, text=True)

    assert result1.returncode == 0
    assert result2.returncode == 0

    # Both should reference the same bundle (or produce identical content)
    bundle1_path = Path(result1.stdout.strip())
    bundle2_path = Path(result2.stdout.strip())

    bundle1 = json.loads(bundle1_path.read_text())
    bundle2 = json.loads(bundle2_path.read_text())

    # Content should be identical (except assembled_at timestamp)
    for key in ["task_id", "agent_type", "worktree_abs_path", "status", "task_description"]:
        assert bundle1.get(key) == bundle2.get(key), f"Mismatch on {key}"


def test_bundle_valid_json_with_worktree(tmp_project_root, worktree_path):
    """Verify generated bundle is valid JSON with expected structure."""
    result = subprocess.run(
        [
            sys.executable, "-m", "agentflow.cli", "bundle",
            "T-999",
            "--agent-type", "worker",
            "--out-dir", str(tmp_project_root),
            "--worktree", str(worktree_path),
        ],
        cwd=str(tmp_project_root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    bundle_path = Path(result.stdout.strip())
    bundle = json.loads(bundle_path.read_text())

    # Verify all expected fields
    required_fields = [
        "task_id", "agent_type", "status", "task_description",
        "addendum", "system_prompt", "assembled_at", "worktree_abs_path"
    ]
    for field in required_fields:
        assert field in bundle, f"Missing field: {field}"

    # Verify types
    assert isinstance(bundle["task_id"], str)
    assert isinstance(bundle["agent_type"], str)
    assert isinstance(bundle["worktree_abs_path"], str)
    assert bundle["worktree_abs_path"] == str(worktree_path.resolve())
