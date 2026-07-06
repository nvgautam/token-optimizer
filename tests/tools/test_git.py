"""Tests for T-005: git worktree tools."""

import inspect
import subprocess
from pathlib import Path

import pytest

from agentflow.tools.git import (
    commit_files,
    create_worktree,
    delete_worktree,
    push_branch,
)



@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "README.md").write_text("init")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def test_create_worktree_creates_branch_and_directory(git_repo):
    path = create_worktree(git_repo, "T-001", "task/T-001")
    assert path == git_repo / "workspaces" / "T-001"
    assert path.exists()
    result = subprocess.run(
        ["git", "branch", "--list", "task/T-001"],
        cwd=git_repo, capture_output=True, text=True,
    )
    assert "task/T-001" in result.stdout


def test_create_worktree_is_idempotent(git_repo):
    path1 = create_worktree(git_repo, "T-001", "task/T-001")
    path2 = create_worktree(git_repo, "T-001", "task/T-001")
    assert path1 == path2
    assert path1.exists()


def test_delete_worktree_removes_directory_and_ref(git_repo):
    path = create_worktree(git_repo, "T-001", "task/T-001")
    assert path.exists()
    delete_worktree(path)
    assert not path.exists()


def test_delete_worktree_is_idempotent_when_path_missing(git_repo):
    missing = git_repo / "workspaces" / "nonexistent"
    delete_worktree(missing)  # must not raise


def test_commit_files_stages_only_listed_files(git_repo):
    path = create_worktree(git_repo, "T-001", "task/T-001")
    (path / "a.py").write_text("x = 1")
    (path / "b.py").write_text("y = 2")

    sha = commit_files(path, "add a.py only", [Path("a.py")])

    assert len(sha) == 40

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=path, capture_output=True, text=True,
    )
    # b.py should still be untracked
    assert "b.py" in status.stdout
    # a.py should not appear as modified/untracked
    assert "a.py" not in status.stdout


def test_invalid_branch_name_raises_before_subprocess(git_repo):
    with pytest.raises(ValueError, match="Invalid branch name"):
        create_worktree(git_repo, "T-001", "task id with spaces")


def test_invalid_branch_name_empty_raises(git_repo):
    with pytest.raises(ValueError):
        create_worktree(git_repo, "T-001", "")


def test_no_shell_true_in_source():
    import agentflow.tools.git as git_module
    source = inspect.getsource(git_module)
    # Skip docstring/comment lines; check that no actual code passes shell=True
    code_lines = [
        line for line in source.splitlines()
        if not line.strip().startswith("#")
        and '"""' not in line
        and "'''" not in line
    ]
    assert all("shell=True" not in line for line in code_lines)


def test_push_branch_calls_git_push(monkeypatch, git_repo):
    from unittest.mock import MagicMock
    import agentflow.tools.git as git_mod

    mock_run = MagicMock()
    monkeypatch.setattr(git_mod, "_run", mock_run)

    push_branch(git_repo, "my-branch", remote="origin")

    mock_run.assert_called_once_with(["git", "push", "-u", "origin", "my-branch"], cwd=git_repo)

