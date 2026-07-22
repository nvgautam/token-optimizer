"""T-322: Verify common oracle spec files exist and skill files reference them."""
import pathlib
import pytest

REPO = pathlib.Path(__file__).parents[2]
COMMON = REPO / "commands" / "common" / "oracle"
CLAUDE_ORACLE = REPO / "commands" / "claude" / "oracle.md"
GEMINI_ORACLE = REPO / "commands" / "gemini" / "skills" / "oracle" / "SKILL.md"

COMMON_FILES = [
    "checklist.md",
    "generation.md",
    "market.md",
    "prioritization.md",
    "phase2_state.md",
]


@pytest.mark.parametrize("filename", COMMON_FILES)
def test_common_file_exists(filename):
    path = COMMON / filename
    assert path.exists(), f"Missing common spec: {path}"


@pytest.mark.parametrize("filename", COMMON_FILES)
def test_common_file_nonempty(filename):
    path = COMMON / filename
    assert path.stat().st_size > 0, f"Empty common spec: {path}"


@pytest.mark.parametrize("filename", COMMON_FILES)
def test_claude_oracle_references_common(filename):
    text = CLAUDE_ORACLE.read_text()
    stem = filename  # e.g. "checklist.md"
    assert f"commands/common/oracle/{stem}" in text, (
        f"claude/oracle.md does not reference commands/common/oracle/{stem}"
    )


@pytest.mark.parametrize("filename", ["checklist.md", "generation.md", "market.md"])
def test_gemini_oracle_references_common(filename):
    text = GEMINI_ORACLE.read_text()
    assert f"commands/common/oracle/{filename}" in text, (
        f"gemini SKILL.md does not reference commands/common/oracle/{filename}"
    )


def test_claude_oracle_no_stale_claude_paths():
    """claude/oracle.md must not reference the old provider-specific oracle/ subdir for spec files."""
    text = CLAUDE_ORACLE.read_text()
    stale_patterns = [
        "commands/claude/oracle/checklist.md",
        "commands/claude/oracle/generation.md",
        "commands/claude/oracle/market.md",
        "commands/claude/oracle/prioritization.md",
        "commands/claude/oracle/phase2_state.md",
    ]
    for pat in stale_patterns:
        assert pat not in text, (
            f"claude/oracle.md still references old path: {pat}"
        )


def test_gemini_oracle_no_stale_gemini_paths():
    """gemini SKILL.md must not reference the old provider-specific oracle/ subdir for spec files."""
    text = GEMINI_ORACLE.read_text()
    stale_patterns = [
        "commands/gemini/oracle/checklist.md",
        "commands/gemini/oracle/generation.md",
        "commands/gemini/oracle/market.md",
    ]
    for pat in stale_patterns:
        assert pat not in text, (
            f"gemini SKILL.md still references old path: {pat}"
        )


def test_common_checklist_content():
    """Common checklist must contain the 24-item section header."""
    text = (COMMON / "checklist.md").read_text()
    assert "24 NFR Items" in text


def test_common_generation_content():
    """Common generation must contain tasks.json schema section."""
    text = (COMMON / "generation.md").read_text()
    assert "tasks.json schema" in text


def test_common_market_content():
    """Common market must have all three segments."""
    text = (COMMON / "market.md").read_text()
    assert "## Consumer" in text
    assert "## SMB" in text
    assert "## Enterprise" in text


def test_common_prioritization_content():
    """Common prioritization must contain disjoint OWNS check rule."""
    text = (COMMON / "prioritization.md").read_text()
    assert "Disjoint OWNS Check" in text


def test_common_phase2_state_content():
    """Common phase2_state must contain auto-commit rule."""
    text = (COMMON / "phase2_state.md").read_text()
    assert "Auto-commit rule" in text
