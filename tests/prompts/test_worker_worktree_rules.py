"""
Test worker agent worktree rules are documented.

Validates that worker guidelines explicitly forbid `pip install -e .`
in worktrees and mandate `python -m pytest` for testing.
"""

import pytest
from pathlib import Path


@pytest.fixture
def repo_root():
    """Return the repository root directory."""
    # The repo root is 5 levels up from tests/prompts/test_worker_worktree_rules.py
    # prompts -> tests -> task-T-346 -> worktrees -> .claude -> token-optimizer
    current = Path(__file__).resolve().parent
    for _ in range(5):
        current = current.parent
    return current


def test_worker_system_forbids_editable_install(repo_root):
    """Verify worker_system.md forbids pip install -e . in worktrees."""
    worker_system = repo_root / "commands/claude/worker_system.md"
    assert worker_system.exists(), f"File not found: {worker_system}"

    content = worker_system.read_text()

    # Check for prohibition of editable install
    assert "pip install -e ." in content or "editable install" in content.lower(), \
        "worker_system.md must contain prohibition of 'pip install -e .' in worktrees"


def test_worker_system_mandates_python_m_pytest(repo_root):
    """Verify worker_system.md mandates python -m pytest for testing."""
    worker_system = repo_root / "commands/claude/worker_system.md"
    assert worker_system.exists(), f"File not found: {worker_system}"

    content = worker_system.read_text()

    # Check for mandate of python -m pytest
    assert "python -m pytest" in content, \
        "worker_system.md must contain mandate to use 'python -m pytest' for testing in worktrees"


def test_worker_system_md_forbids_editable_install(repo_root):
    """Verify commands/claude/worker/system.md forbids pip install -e . in worktrees."""
    worker_system = repo_root / "commands/claude/worker/system.md"
    assert worker_system.exists(), f"File not found: {worker_system}"

    content = worker_system.read_text()

    # Check for prohibition of editable install
    assert "pip install -e ." in content or "editable install" in content.lower(), \
        "commands/claude/worker/system.md must contain prohibition of 'pip install -e .' in worktrees"


def test_worker_system_md_mandates_python_m_pytest(repo_root):
    """Verify commands/claude/worker/system.md mandates python -m pytest for testing."""
    worker_system = repo_root / "commands/claude/worker/system.md"
    assert worker_system.exists(), f"File not found: {worker_system}"

    content = worker_system.read_text()

    # Check for mandate of python -m pytest
    assert "python -m pytest" in content, \
        "commands/claude/worker/system.md must contain mandate to use 'python -m pytest' for testing in worktrees"


def test_testing_guide_forbids_editable_install(repo_root):
    """Verify testing_guide.md forbids pip install -e . in worktrees."""
    testing_guide = repo_root / "commands/claude/worker/testing_guide.md"
    assert testing_guide.exists(), f"File not found: {testing_guide}"

    content = testing_guide.read_text()

    # Check for prohibition of editable install
    assert "pip install -e ." in content or "editable install" in content.lower(), \
        "testing_guide.md must contain prohibition of 'pip install -e .' in worktrees"


def test_testing_guide_mandates_python_m_pytest(repo_root):
    """Verify testing_guide.md mandates python -m pytest for testing."""
    testing_guide = repo_root / "commands/claude/worker/testing_guide.md"
    assert testing_guide.exists(), f"File not found: {testing_guide}"

    content = testing_guide.read_text()

    # Check for mandate of python -m pytest
    assert "python -m pytest" in content, \
        "testing_guide.md must contain mandate to use 'python -m pytest' for testing in worktrees"
