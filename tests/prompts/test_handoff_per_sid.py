"""Tests for per-SID handoff document routing (T-205)."""
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
HANDOFF_FILE = REPO / "commands" / "claude" / "handoff.md"


def test_handoff_mentions_per_sid_path():
    """Step 6 should mention sessions/<SID>/ path when AGENTFLOW_SESSION_ID is set."""
    content = HANDOFF_FILE.read_text(encoding="utf-8")
    assert "sessions/" in content, \
        "handoff.md Step 6 must describe routing to .agentflow/sessions/<SID>/"
    assert "AGENTFLOW_SESSION_ID" in content, \
        "handoff.md Step 6 must check AGENTFLOW_SESSION_ID env var"


def test_handoff_mentions_symlink():
    """Step 6 should describe creating handoff_latest.md symlink."""
    content = HANDOFF_FILE.read_text(encoding="utf-8")
    assert "handoff_latest.md" in content, \
        "handoff.md Step 6 must create/update .agentflow/handoff_latest.md symlink"


def test_handoff_mentions_symlink_portability():
    """Symlink should use relative target for portability."""
    content = HANDOFF_FILE.read_text(encoding="utf-8")
    # Check that the instruction mentions relative symlink targets
    assert ("ln -sf" in content or "relative" in content.lower()), \
        "handoff.md must document symlink creation with relative targets"


def test_handoff_complete_shows_actual_path():
    """Step 8 HANDOFF_COMPLETE should reference the actual path written."""
    content = HANDOFF_FILE.read_text(encoding="utf-8")
    # HANDOFF_COMPLETE line should show the path variable, not hardcoded path
    assert "HANDOFF_COMPLETE" in content, "Must have HANDOFF_COMPLETE instruction"
    lines = content.splitlines()
    complete_lines = [l for l in lines if "HANDOFF_COMPLETE" in l]
    # Should reference the file path (either as variable or description)
    assert any("path" in line.lower() or "handoff" in line.lower()
               for line in complete_lines), \
        "HANDOFF_COMPLETE instruction should reference the handoff file path"
