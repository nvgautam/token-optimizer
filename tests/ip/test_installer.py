"""Tests for agentflow.ip.installer — hook installation/uninstall into ~/.claude/settings.json."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from agentflow.ip.installer import install, uninstall

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PROJECT_HOOKS = {
    "UserPromptSubmit": [
        {
            "hooks": [
                {"type": "command", "command": "agentflow hooks idx_reminder"},
                {"type": "command", "command": "agentflow hooks verbosity_reminder"},
            ]
        }
    ],
    "PostToolUse": [
        {
            "matcher": "Write",
            "hooks": [
                {"type": "command", "command": "agentflow hooks write_indexer"},
                {"type": "command", "command": "agentflow hooks size_check"},
            ],
        }
    ],
}


def _make_project_settings(tmp_path: Path, hooks: dict) -> Path:
    """Write a project .claude/settings.json with specified hooks."""
    claude_dir = tmp_path / "project" / ".claude"
    claude_dir.mkdir(parents=True)
    settings = claude_dir / "settings.json"
    settings.write_text(json.dumps({"hooks": hooks}), encoding="utf-8")
    return tmp_path / "project"


def _home_settings(tmp_path: Path) -> Path:
    return tmp_path / "home" / ".claude" / "settings.json"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_install_creates_settings_when_absent(tmp_path):
    """install() creates ~/.claude/settings.json when it doesn't exist."""
    project_root = _make_project_settings(tmp_path, SAMPLE_PROJECT_HOOKS)
    home = tmp_path / "home"
    home.mkdir()

    with patch("agentflow.ip.installer.Path.home", return_value=home):
        install(project_root=project_root)

    settings_path = home / ".claude" / "settings.json"
    assert settings_path.exists()
    data = json.loads(settings_path.read_text())
    hooks = data["hooks"]

    # agentflow hooks should be present
    up_hooks = hooks["UserPromptSubmit"][0]["hooks"]
    commands = [h["command"] for h in up_hooks]
    assert "agentflow hooks idx_reminder" in commands
    assert "agentflow hooks verbosity_reminder" in commands


def test_install_merges_without_clobbering(tmp_path):
    """install() adds agentflow hooks without removing existing user hooks."""
    project_root = _make_project_settings(tmp_path, SAMPLE_PROJECT_HOOKS)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)

    # Pre-existing user hook
    existing = {
        "hooks": {
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {"type": "command", "command": "my-custom-hook"}
                    ]
                }
            ]
        }
    }
    (home / ".claude" / "settings.json").write_text(json.dumps(existing), encoding="utf-8")

    with patch("agentflow.ip.installer.Path.home", return_value=home):
        install(project_root=project_root)

    data = json.loads((home / ".claude" / "settings.json").read_text())
    hooks = data["hooks"]

    # Find the "UserPromptSubmit" block list
    up_list = hooks["UserPromptSubmit"]
    all_commands = [h["command"] for block in up_list for h in block["hooks"]]

    # User hook preserved
    assert "my-custom-hook" in all_commands
    # Agentflow hooks added
    assert "agentflow hooks idx_reminder" in all_commands


def test_install_is_idempotent(tmp_path):
    """install() twice produces identical result — no duplicate hook entries."""
    project_root = _make_project_settings(tmp_path, SAMPLE_PROJECT_HOOKS)
    home = tmp_path / "home"
    home.mkdir()

    with patch("agentflow.ip.installer.Path.home", return_value=home):
        install(project_root=project_root)
        install(project_root=project_root)

    data = json.loads((home / ".claude" / "settings.json").read_text())
    hooks = data["hooks"]

    # No duplicate commands in any hook block
    for event_type, blocks in hooks.items():
        for block in blocks:
            commands = [h["command"] for h in block["hooks"]]
            assert len(commands) == len(set(commands)), (
                f"Duplicates found in {event_type}: {commands}"
            )


def test_uninstall_removes_only_agentflow_entries(tmp_path):
    """uninstall() removes only 'agentflow hooks' entries; user hooks survive."""
    project_root = _make_project_settings(tmp_path, SAMPLE_PROJECT_HOOKS)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)

    # Pre-existing user hook alongside agentflow hooks
    existing = {
        "hooks": {
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {"type": "command", "command": "my-custom-hook"},
                        {"type": "command", "command": "agentflow hooks idx_reminder"},
                    ]
                }
            ]
        }
    }
    (home / ".claude" / "settings.json").write_text(json.dumps(existing), encoding="utf-8")

    with patch("agentflow.ip.installer.Path.home", return_value=home):
        uninstall()

    data = json.loads((home / ".claude" / "settings.json").read_text())
    hooks = data["hooks"]

    up_list = hooks.get("UserPromptSubmit", [])
    all_commands = [h["command"] for block in up_list for h in block["hooks"]]

    # User hook preserved
    assert "my-custom-hook" in all_commands
    # Agentflow hook removed
    assert not any("agentflow hooks" in cmd for cmd in all_commands)


def test_uninstall_noop_when_not_installed(tmp_path):
    """uninstall() with no agentflow hooks → no error, settings unchanged."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)

    original = {
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "my-custom-hook"}]}
            ]
        }
    }
    settings_path = home / ".claude" / "settings.json"
    settings_path.write_text(json.dumps(original), encoding="utf-8")

    with patch("agentflow.ip.installer.Path.home", return_value=home):
        uninstall()  # should not raise

    data = json.loads(settings_path.read_text())
    assert data == original


def test_uninstall_noop_when_settings_absent(tmp_path):
    """uninstall() is a no-op if ~/.claude/settings.json doesn't exist."""
    home = tmp_path / "home"
    home.mkdir()

    with patch("agentflow.ip.installer.Path.home", return_value=home):
        uninstall()  # must not raise


def test_install_atomic_write(tmp_path):
    """install() uses temp-file + os.replace — no partial writes."""
    project_root = _make_project_settings(tmp_path, SAMPLE_PROJECT_HOOKS)
    home = tmp_path / "home"
    home.mkdir()

    written_files = []
    real_replace = os.replace

    def spy_replace(src, dst):
        written_files.append((src, dst))
        real_replace(src, dst)

    with patch("agentflow.ip.installer.Path.home", return_value=home), \
         patch("agentflow.ip.installer.os.replace", side_effect=spy_replace):
        install(project_root=project_root)

    assert written_files, "os.replace was never called — atomic write not used"
    src, dst = written_files[-1]
    # src should be a temp file (not the final path)
    assert src != dst
    # dst should be the settings.json path
    assert dst == str(home / ".claude" / "settings.json")


def test_transform_command_converts_project_hook():
    """_transform_command converts raw CLAUDE_PROJECT_DIR hooks to binary form."""
    from agentflow.ip.installer import _transform_command
    raw = 'python3 "$CLAUDE_PROJECT_DIR/agentflow/hooks/read_check.py"'
    assert _transform_command(raw) == "agentflow hooks read_check"


def test_transform_command_passthrough_binary():
    """Already-transformed commands are returned unchanged."""
    from agentflow.ip.installer import _transform_command
    assert _transform_command("agentflow hooks idx_reminder") == "agentflow hooks idx_reminder"


def test_transform_command_passthrough_other():
    """Non-agentflow commands are returned unchanged."""
    from agentflow.ip.installer import _transform_command
    assert _transform_command("custom-hook --flag") == "custom-hook --flag"


def test_install_preserves_non_hook_settings(tmp_path):
    """install() leaves other top-level keys (e.g. permissions) untouched."""
    project_root = _make_project_settings(tmp_path, SAMPLE_PROJECT_HOOKS)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)

    existing = {
        "permissions": {"allow": ["Bash(git:*)"]},
        "hooks": {}
    }
    (home / ".claude" / "settings.json").write_text(json.dumps(existing), encoding="utf-8")

    with patch("agentflow.ip.installer.Path.home", return_value=home):
        install(project_root=project_root)

    data = json.loads((home / ".claude" / "settings.json").read_text())
    assert data.get("permissions") == {"allow": ["Bash(git:*)"]}
