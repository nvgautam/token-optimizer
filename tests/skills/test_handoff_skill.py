"""Tests for T-025: handoff skill provider files."""
import os
import stat
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

CLAUDE_HANDOFF = REPO_ROOT / "agentflow/skills/providers/claude/handoff.md"
GEMINI_SKILL = REPO_ROOT / "agentflow/skills/providers/gemini/handoff/SKILL.md"
GEMINI_SCRIPT = REPO_ROOT / "agentflow/skills/providers/gemini/handoff/scripts/run_handoff.sh"


# --- Claude skill ---

def test_claude_handoff_exists():
    """claude/handoff.md must exist."""
    assert CLAUDE_HANDOFF.exists(), f"Missing: {CLAUDE_HANDOFF}"


def test_claude_handoff_valid_utf8():
    """claude/handoff.md must be valid UTF-8."""
    content = CLAUDE_HANDOFF.read_bytes()
    content.decode("utf-8")  # raises UnicodeDecodeError if invalid


def test_claude_handoff_contains_handoff_complete():
    """claude/handoff.md must contain the HANDOFF_COMPLETE output instruction."""
    content = CLAUDE_HANDOFF.read_text(encoding="utf-8")
    assert "HANDOFF_COMPLETE" in content, "claude/handoff.md missing HANDOFF_COMPLETE signal"


def test_claude_handoff_uses_agentflow_paths():
    """claude/handoff.md must reference .agentflow/ paths, not .claude/memory/."""
    content = CLAUDE_HANDOFF.read_text(encoding="utf-8")
    assert ".agentflow/" in content, "claude/handoff.md must reference .agentflow/ paths"
    # Must not instruct writing to .claude/memory/ as session state
    # (it may mention it to say NOT to use it — check for .agentflow/ presence is the key requirement)


def test_claude_handoff_contains_handoff_recommended():
    """claude/handoff.md must contain the HANDOFF RECOMMENDED proactive signal."""
    content = CLAUDE_HANDOFF.read_text(encoding="utf-8")
    assert "HANDOFF RECOMMENDED" in content, "claude/handoff.md missing HANDOFF RECOMMENDED signal"


def test_claude_handoff_recommended_has_reason_format():
    """claude/handoff.md must show HANDOFF RECOMMENDED: <reason> format."""
    content = CLAUDE_HANDOFF.read_text(encoding="utf-8")
    assert "HANDOFF RECOMMENDED: " in content, (
        "claude/handoff.md must show 'HANDOFF RECOMMENDED: <reason>' format"
    )


# --- Gemini skill ---

def test_gemini_skill_exists():
    """gemini/handoff/SKILL.md must exist."""
    assert GEMINI_SKILL.exists(), f"Missing: {GEMINI_SKILL}"


def test_gemini_skill_valid_utf8():
    """gemini/handoff/SKILL.md must be valid UTF-8."""
    content = GEMINI_SKILL.read_bytes()
    content.decode("utf-8")


def test_gemini_skill_contains_handoff_complete():
    """gemini/handoff/SKILL.md must contain the HANDOFF_COMPLETE output instruction."""
    content = GEMINI_SKILL.read_text(encoding="utf-8")
    assert "HANDOFF_COMPLETE" in content, "gemini/SKILL.md missing HANDOFF_COMPLETE signal"


def test_gemini_skill_contains_handoff_recommended():
    """gemini/handoff/SKILL.md must contain the HANDOFF RECOMMENDED proactive signal."""
    content = GEMINI_SKILL.read_text(encoding="utf-8")
    assert "HANDOFF RECOMMENDED" in content, "gemini/SKILL.md missing HANDOFF RECOMMENDED signal"


def test_gemini_skill_recommended_has_reason_format():
    """gemini/handoff/SKILL.md must show HANDOFF RECOMMENDED: <reason> format."""
    content = GEMINI_SKILL.read_text(encoding="utf-8")
    assert "HANDOFF RECOMMENDED: " in content, (
        "gemini/SKILL.md must show 'HANDOFF RECOMMENDED: <reason>' format"
    )


# --- Gemini shell script ---

def test_gemini_script_exists():
    """gemini/handoff/scripts/run_handoff.sh must exist."""
    assert GEMINI_SCRIPT.exists(), f"Missing: {GEMINI_SCRIPT}"


def test_gemini_script_is_executable():
    """run_handoff.sh must be executable."""
    mode = GEMINI_SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR, "run_handoff.sh is not executable (missing user execute bit)"


def test_gemini_script_contains_handoff_complete():
    """run_handoff.sh must contain the HANDOFF_COMPLETE signal."""
    content = GEMINI_SCRIPT.read_text(encoding="utf-8")
    assert "HANDOFF_COMPLETE" in content, "run_handoff.sh missing HANDOFF_COMPLETE signal"
