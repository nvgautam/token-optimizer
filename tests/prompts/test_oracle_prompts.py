"""Tests for T-013: oracle prompt files existence, size, and content."""

import re
from pathlib import Path

ORACLE_PROMPTS_ROOT = (
    Path(__file__).parent.parent.parent / "agentflow" / "prompts" / "oracle" / "v1"
)

ORACLE_PROMPT_FILES = [
    "system.md",
    "market.md",
    "checklist.md",
    "generation.md",
]


def _path(filename: str) -> Path:
    return ORACLE_PROMPTS_ROOT / filename


def _read(filename: str) -> str:
    return _path(filename).read_text(encoding="utf-8")


def _line_count(filename: str) -> int:
    return len(_read(filename).splitlines())


def test_all_oracle_prompt_files_exist():
    """All four oracle prompt files must exist."""
    for f in ORACLE_PROMPT_FILES:
        assert _path(f).exists(), f"Missing oracle prompt file: {f}"


def test_all_oracle_prompt_files_are_valid_utf8():
    """All files must be readable as valid UTF-8."""
    for f in ORACLE_PROMPT_FILES:
        content = _read(f)
        assert isinstance(content, str), f"{f} could not be decoded as UTF-8"
        assert len(content) > 0, f"{f} is empty"


def test_no_oracle_prompt_file_exceeds_150_lines():
    """No prompt file may exceed 150 lines."""
    for f in ORACLE_PROMPT_FILES:
        count = _line_count(f)
        assert count <= 150, f"{f} has {count} lines (ceiling: 150)"


def test_system_md_contains_market_segment():
    """system.md must reference market segment branching."""
    content = _read("system.md").lower()
    assert "segment" in content or "market" in content, (
        "system.md must contain market segment section"
    )


def test_system_md_contains_prompt_injection_question():
    """system.md must include the prompt injection question."""
    content = _read("system.md").lower()
    assert "untrusted" in content or "prompt injection" in content, (
        "system.md must contain the prompt injection question"
    )


def test_system_md_contains_verbosity_instruction():
    """system.md must include the verbosity instruction."""
    content = _read("system.md").lower()
    assert "concise" in content, (
        "system.md must contain the verbosity instruction ('concise')"
    )


def test_checklist_has_at_least_23_section_headers():
    """checklist.md must have at least 23 '## ' section headers."""
    content = _read("checklist.md")
    count = sum(1 for line in content.splitlines() if line.startswith("## "))
    assert count >= 23, (
        f"checklist.md has {count} '## ' headers; need at least 23"
    )


def test_generation_md_contains_all_status_keywords():
    """generation.md must contain RESOLVED, UNRESOLVED, and DEFERRED."""
    content = _read("generation.md")
    for keyword in ("RESOLVED", "UNRESOLVED", "DEFERRED"):
        assert keyword in content, (
            f"generation.md is missing the keyword: {keyword}"
        )


def test_no_oracle_prompt_contains_hardcoded_secrets():
    """No oracle prompt file may contain a hardcoded secret pattern."""
    pattern = re.compile(
        r"(key|token|secret|password)\s*=\s*['\"][^'\"]{8,}", re.IGNORECASE
    )
    for f in ORACLE_PROMPT_FILES:
        content = _read(f)
        matches = pattern.findall(content)
        assert not matches, (
            f"{f} contains potential hardcoded secret pattern: {matches}"
        )
