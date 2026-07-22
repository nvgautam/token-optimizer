"""T-323: Verify provider-agnostic coding standards document and worker prompts integration."""
import pathlib

REPO = pathlib.Path(__file__).parents[2]
CODING_STANDARDS = REPO / "commands" / "common" / "coding_standards.md"
CLAUDE_WORKER = REPO / "commands" / "claude" / "worker" / "system.md"
CLAUDE_WORKER_SYSTEM = REPO / "commands" / "claude" / "worker_system.md"
GEMINI_ORCHESTRATE = REPO / "commands" / "gemini" / "skills" / "orchestrate" / "SKILL.md"


def test_coding_standards_file_exists():
    """Verify that coding_standards.md exists and is not empty."""
    assert CODING_STANDARDS.exists(), f"Missing coding standards: {CODING_STANDARDS}"
    assert CODING_STANDARDS.stat().st_size > 0, "Coding standards file is empty"


def test_coding_standards_no_syntax_errors():
    """Verify that the coding standards document contains no basic markdown syntax errors."""
    text = CODING_STANDARDS.read_text(encoding="utf-8")
    # All code blocks must be closed
    assert text.count("```") % 2 == 0, "Unclosed code block in coding_standards.md"


def test_claude_worker_references_standards():
    """Verify that the Claude worker prompt references the common coding standards."""
    text = CLAUDE_WORKER.read_text(encoding="utf-8")
    assert "commands/common/coding_standards.md" in text, (
        "Claude worker system prompt does not reference commands/common/coding_standards.md"
    )


def test_claude_worker_system_references_standards():
    """Verify that the Claude worker_system.md copy references the common coding standards."""
    text = CLAUDE_WORKER_SYSTEM.read_text(encoding="utf-8")
    assert "commands/common/coding_standards.md" in text, (
        "Claude worker_system.md copy does not reference commands/common/coding_standards.md"
    )


def test_gemini_orchestrate_references_standards():
    """Verify that the Gemini orchestrator skill references the common coding standards."""
    text = GEMINI_ORCHESTRATE.read_text(encoding="utf-8")
    assert "commands/common/coding_standards.md" in text, (
        "Gemini orchestrate skill does not reference commands/common/coding_standards.md"
    )
