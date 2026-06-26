"""Tests for T-015: reviewer and orchestrator prompt files."""

import re
from pathlib import Path

REVIEWER_ROOT = Path(__file__).parent.parent.parent / "agentflow" / "reviewer" / "prompts" / "v1"
ORCHESTRATOR_ROOT = Path(__file__).parent.parent.parent / "agentflow" / "orchestrator" / "prompts" / "v1"

PROMPT_FILES = {
    "reviewer/code_review.md": REVIEWER_ROOT / "code_review.md",
    "reviewer/security_review.md": REVIEWER_ROOT / "security_review.md",
    "reviewer/test_review.md": REVIEWER_ROOT / "test_review.md",
    "orchestrator/system.md": ORCHESTRATOR_ROOT / "system.md",
    "orchestrator/planning.md": ORCHESTRATOR_ROOT / "planning.md",
}


def _read(key: str) -> str:
    return PROMPT_FILES[key].read_text(encoding="utf-8")


def _line_count(key: str) -> int:
    return len(_read(key).splitlines())


def test_all_prompt_files_exist_and_are_valid_utf8():
    for key, path in PROMPT_FILES.items():
        assert path.exists(), f"Missing prompt file: {key} at {path}"
        # Validate UTF-8 by reading — raises UnicodeDecodeError if invalid
        path.read_text(encoding="utf-8")


def test_no_prompt_file_exceeds_150_lines():
    for key in PROMPT_FILES:
        count = _line_count(key)
        assert count <= 150, f"{key} has {count} lines (ceiling: 150)"


def test_security_review_references_owasp():
    content = _read("reviewer/security_review.md")
    assert "OWASP" in content or "owasp" in content.lower(), (
        "security_review.md must reference OWASP Top 10"
    )


def test_security_review_contains_untrusted_diff_rule():
    content = _read("reviewer/security_review.md")
    # Must contain "untrusted" in proximity to "diff" or "PR diff"
    assert "untrusted" in content.lower(), (
        "security_review.md must contain untrusted-diff instruction"
    )
    assert "diff" in content.lower() or "PR diff" in content, (
        "security_review.md must reference PR diff as untrusted data"
    )


def test_planning_md_contains_milestone_decomposition_format():
    content = _read("orchestrator/planning.md")
    assert "milestone" in content.lower(), (
        "planning.md must contain milestone decomposition format"
    )
    assert "round" in content.lower(), (
        "planning.md must describe parallelism rounds"
    )


def test_orchestrator_system_contains_staff_engineering_lead_persona():
    content = _read("orchestrator/system.md")
    assert "Staff Engineering Lead" in content or "Staff Engineer" in content, (
        "orchestrator system.md must declare Staff Engineering Lead persona"
    )


def test_orchestrator_system_contains_escalation_criteria():
    content = _read("orchestrator/system.md")
    assert "escalate" in content.lower(), (
        "orchestrator system.md must contain escalation criteria"
    )
    has_second = "second" in content.lower()
    has_critical = "CRITICAL" in content or "critical" in content.lower()
    assert has_second or has_critical, (
        "orchestrator system.md must reference second rework failure or CRITICAL findings as escalation trigger"
    )


def test_no_prompt_contains_hardcoded_secret_pattern():
    pattern = re.compile(r'(key|token|secret|password)\s*=\s*[\'"][^\'"]{8,}', re.IGNORECASE)
    for key in PROMPT_FILES:
        content = _read(key)
        matches = pattern.findall(content)
        assert not matches, f"{key} contains potential hardcoded secret pattern: {matches}"
