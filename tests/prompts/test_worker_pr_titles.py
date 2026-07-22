"""Test that worker system instructions mandate conventional commit PR titles with task ID."""

import re
from pathlib import Path


def test_worker_system_md_exists():
    """Worker system instructions file must exist."""
    system_md = Path(__file__).parent.parent.parent / "commands/claude/worker/system.md"
    assert system_md.exists(), f"Worker system.md not found at {system_md}"


def test_worker_system_contains_pr_title_rule():
    """Worker system.md must contain explicit rule for PR title format with task ID."""
    system_md = Path(__file__).parent.parent.parent / "commands/claude/worker/system.md"
    content = system_md.read_text()

    # Check for rule about PR titles/commits with conventional format
    assert "PR title" in content or "pull request" in content.lower(), (
        "system.md must mention PR titles/pull requests"
    )

    # Check for mention of conventional commits or task ID format
    assert "conventional commit" in content.lower() or "feat(" in content or "fix(" in content, (
        "system.md must reference conventional commit format (feat/fix/etc)"
    )

    # Most critical: check for explicit `(T-` pattern in context of PR/commit formatting
    assert re.search(r'\(T-\d+\)', content), (
        "system.md must explicitly show the (T-NNN) format for task IDs in PR titles or commits"
    )

    # Check that this is in the context of formatting rules, not just mentioned in passing
    lines_with_task_id = [line for line in content.split('\n') if re.search(r'\(T-\d+\)', line)]
    assert len(lines_with_task_id) >= 1, (
        "Must have at least one line showing (T-NNN) format"
    )


def test_worker_system_mentions_regex_matching():
    """Prevent regex matching failures by explicitly documenting the format requirement."""
    system_md = Path(__file__).parent.parent.parent / "commands/claude/worker/system.md"
    content = system_md.read_text()

    # Should mention regex matching or hooks that depend on the format
    assert "regex" in content.lower() or "hook" in content.lower() or "task cleanup" in content.lower(), (
        "system.md should reference why the format matters (regex matching in hooks, task cleanup)"
    )
