"""Tests for T-004: prompt files existence, size, and content."""

import re
from pathlib import Path

PROMPTS_ROOT = Path(__file__).parent.parent.parent / "agentflow" / "prompts"

PROMPT_FILES = [
    "oracle/v1/system.md",
    "oracle/v1/checklist.md",
    "oracle/v1/generation.md",
    "worker/v1/system.md",
    "worker/v1/context_bundle.md",
    "worker/v1/testing_guide.md",
    "reviewer/v1/code_review.md",
    "reviewer/v1/security_review.md",
    "reviewer/v1/test_review.md",
]


def _read(relative: str) -> str:
    return (PROMPTS_ROOT / relative).read_text(encoding="utf-8")


def _line_count(relative: str) -> int:
    return len(_read(relative).splitlines())


def test_all_prompt_files_exist():
    for f in PROMPT_FILES:
        assert (PROMPTS_ROOT / f).exists(), f"Missing prompt file: {f}"


def test_no_prompt_file_exceeds_ceiling():
    for f in PROMPT_FILES:
        count = _line_count(f)
        assert count <= 150, f"{f} has {count} lines (ceiling: 150)"


def test_oracle_system_contains_checklist_reference():
    content = _read("oracle/v1/system.md").lower()
    assert "checklist" in content


def test_oracle_checklist_contains_all_sections():
    content = _read("oracle/v1/checklist.md")
    assert "Functional" in content
    assert "Non-functional" in content
    assert "Quality" in content


def test_security_review_references_owasp():
    content = _read("reviewer/v1/security_review.md")
    assert "OWASP" in content or "owasp" in content


def test_testing_guide_contains_tdd_sections():
    content = _read("worker/v1/testing_guide.md").lower()
    assert "red" in content
    assert "behaviour" in content or "behavior" in content
    assert "io mock" in content or "io boundaries" in content


def test_no_prompt_contains_hardcoded_secrets():
    pattern = re.compile(r'(key|token|secret|password)\s*=\s*[\'"][^\'"]{8,}', re.IGNORECASE)
    for f in PROMPT_FILES:
        content = _read(f)
        matches = pattern.findall(content)
        assert not matches, f"{f} contains potential hardcoded secret pattern: {matches}"
