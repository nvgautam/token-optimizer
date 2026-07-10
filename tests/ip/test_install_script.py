"""Tests for install.sh — design partner installer."""

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent


def _run(env_overrides: dict, cwd=None) -> subprocess.CompletedProcess:
    """Run install.sh with given env overrides, capturing stdout+stderr."""
    env = os.environ.copy()
    env.update(env_overrides)
    return subprocess.run(
        ["bash", str(REPO_ROOT / "install.sh")],
        cwd=cwd or REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Test 1 & 2 — existence + executable bit
# ---------------------------------------------------------------------------


def test_install_script_exists():
    assert (REPO_ROOT / "install.sh").exists()


def test_install_script_is_executable():
    assert os.access(REPO_ROOT / "install.sh", os.X_OK)


# ---------------------------------------------------------------------------
# Test 3 — binary copy
# ---------------------------------------------------------------------------


def test_install_copies_binary(tmp_path):
    """Binary at dist/agentflow is copied to AGENTFLOW_INSTALL_DIR."""
    fake_dist = REPO_ROOT / "dist"
    fake_dist.mkdir(exist_ok=True)
    fake_binary = fake_dist / "agentflow"
    fake_binary.write_text("#!/bin/bash\necho fake agentflow\n")
    fake_binary.chmod(0o755)

    install_dir = tmp_path / "bin"
    install_dir.mkdir()

    result = _run(
        {
            "AGENTFLOW_INSTALL_DIR": str(install_dir),
            "CLAUDE_COMMANDS_DIR": str(tmp_path / "cmds"),
            "AGENTFLOW_SKIP_HOOKS": "1",
        }
    )

    assert result.returncode == 0, result.stderr
    assert (install_dir / "agentflow").exists(), (
        f"binary not copied; stdout={result.stdout!r} stderr={result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Test 4 — skills copy
# ---------------------------------------------------------------------------


def test_install_copies_skills(tmp_path):
    """Skills from commands/claude/ are copied to CLAUDE_COMMANDS_DIR/claude/."""
    # Ensure a fake binary so the binary-copy step doesn't fail
    fake_dist = REPO_ROOT / "dist"
    fake_dist.mkdir(exist_ok=True)
    fake_binary = fake_dist / "agentflow"
    if not fake_binary.exists():
        fake_binary.write_text("#!/bin/bash\necho fake\n")
        fake_binary.chmod(0o755)

    cmds_dir = tmp_path / "cmds"
    cmds_dir.mkdir()

    result = _run(
        {
            "AGENTFLOW_INSTALL_DIR": str(tmp_path / "bin"),
            "CLAUDE_COMMANDS_DIR": str(cmds_dir),
            "AGENTFLOW_SKIP_HOOKS": "1",
        }
    )

    assert result.returncode == 0, result.stderr

    # At least one .md file should be present under cmds_dir/claude/
    installed = list((cmds_dir / "claude").rglob("*.md"))
    assert installed, (
        f"no skill files copied; stdout={result.stdout!r} stderr={result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Test 5 — hooks skipped when AGENTFLOW_SKIP_HOOKS=1
# ---------------------------------------------------------------------------


def test_install_skips_hooks_when_env_set(tmp_path):
    """AGENTFLOW_SKIP_HOOKS=1 must not trigger the agentflow install hook-merge step."""
    fake_dist = REPO_ROOT / "dist"
    fake_dist.mkdir(exist_ok=True)
    fake_binary = fake_dist / "agentflow"
    if not fake_binary.exists():
        fake_binary.write_text("#!/bin/bash\necho fake\n")
        fake_binary.chmod(0o755)

    result = _run(
        {
            "AGENTFLOW_INSTALL_DIR": str(tmp_path / "bin"),
            "CLAUDE_COMMANDS_DIR": str(tmp_path / "cmds"),
            "AGENTFLOW_SKIP_HOOKS": "1",
        }
    )

    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    assert "hooks installed" not in combined.lower(), (
        f"hook-merge step ran despite AGENTFLOW_SKIP_HOOKS=1: {combined!r}"
    )


# ---------------------------------------------------------------------------
# Test 6 — graceful when binary absent
# ---------------------------------------------------------------------------


def test_install_no_binary_graceful(tmp_path):
    """Missing dist/agentflow → exit 0 with a warning, no hard failure."""
    # Temporarily hide dist/agentflow if it exists by using a fresh temp dir
    # We tell the script to look for the binary in a nonexistent dist path via
    # AGENTFLOW_DIST_DIR (or let the script not find dist/agentflow at all).
    # Simplest approach: use a separate CWD that has no dist/ directory.
    fake_cwd = tmp_path / "fake_repo"
    fake_cwd.mkdir()

    # Copy install.sh only (no dist/)
    import shutil

    shutil.copy(REPO_ROOT / "install.sh", fake_cwd / "install.sh")

    # Create a minimal commands/claude/ so the skills step doesn't error
    (fake_cwd / "commands" / "claude").mkdir(parents=True)
    (fake_cwd / "commands" / "claude" / "README.md").write_text("# skills\n")

    result = subprocess.run(
        ["bash", str(fake_cwd / "install.sh")],
        cwd=fake_cwd,
        env={
            **os.environ,
            "AGENTFLOW_INSTALL_DIR": str(tmp_path / "bin"),
            "CLAUDE_COMMANDS_DIR": str(tmp_path / "cmds"),
            "AGENTFLOW_SKIP_HOOKS": "1",
        },
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"script exited non-zero with no binary present; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "warn" in combined.lower() or "skip" in combined.lower() or "not found" in combined.lower(), (
        f"expected a warning when binary is absent; got: {combined!r}"
    )
