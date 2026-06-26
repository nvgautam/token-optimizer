"""Tests for T-014: worker prompt files existence, size, and content."""

import re
from pathlib import Path

WORKER_PROMPTS = Path(__file__).parent.parent.parent / "agentflow" / "prompts" / "worker" / "v1"

PROMPT_FILES = [
    "system.md",
    "context_bundle.md",
    "testing_guide.md",
]


def _read(name: str) -> str:
    return (WORKER_PROMPTS / name).read_text(encoding="utf-8")


def _line_count(name: str) -> int:
    return len(_read(name).splitlines())


# --- existence and encoding ---

def test_all_worker_prompt_files_exist():
    for f in PROMPT_FILES:
        assert (WORKER_PROMPTS / f).exists(), f"Missing worker prompt file: {f}"


def test_all_worker_prompt_files_are_valid_utf8():
    for f in PROMPT_FILES:
        try:
            _read(f)
        except UnicodeDecodeError as exc:
            raise AssertionError(f"{f} is not valid UTF-8: {exc}") from exc


# --- line count ceiling ---

def test_no_worker_prompt_exceeds_150_lines():
    for f in PROMPT_FILES:
        count = _line_count(f)
        assert count <= 150, f"{f} has {count} lines (ceiling: 150)"


# --- system.md required content ---

def test_system_md_contains_no_re_read_rule():
    content = _read("system.md")
    assert "Do not use the Read tool" in content, (
        "system.md missing no-re-read rule: 'Do not use the Read tool'"
    )


def test_system_md_no_re_read_rule_before_task_section():
    """No-re-read rule must appear before any 'task' or 'persona' heading."""
    content = _read("system.md")
    re_read_pos = content.find("Do not use the Read tool")
    assert re_read_pos != -1, "No-re-read rule not found in system.md"

    # Find position of first task/workflow/persona section heading after the rules block
    first_section_match = re.search(
        r"^##\s+(Persona|TDD|Workflow|Ownership|Security)",
        content,
        re.MULTILINE | re.IGNORECASE,
    )
    if first_section_match:
        assert re_read_pos < first_section_match.start(), (
            "No-re-read rule must appear before the first task/persona section"
        )


def test_system_md_contains_section_only_loading_rule():
    content = _read("system.md")
    has_anchor = "anchor" in content.lower()
    has_section_only = "section only" in content.lower()
    has_never_load = "Never load full" in content
    assert has_anchor or has_section_only or has_never_load, (
        "system.md missing section-only loading rule "
        "(expected 'anchor', 'section only', or 'Never load full')"
    )


def test_system_md_contains_verbosity_instruction():
    content = _read("system.md")
    has_concise = "concise" in content.lower()
    has_code_only = "code and test output only" in content.lower()
    assert has_concise or has_code_only, (
        "system.md missing verbosity instruction "
        "(expected 'concise' or 'code and test output only')"
    )


# --- testing_guide.md required content ---

def test_testing_guide_contains_tdd_red_green():
    content = _read("testing_guide.md").lower()
    assert "red" in content, "testing_guide.md missing TDD 'red' reference"
    assert "green" in content, "testing_guide.md missing TDD 'green' reference"


def test_testing_guide_contains_behaviour_not_implementation():
    content = _read("testing_guide.md").lower()
    assert "behaviour" in content or "behavior" in content, (
        "testing_guide.md missing behaviour-not-implementation reference"
    )


def test_testing_guide_contains_io_mock_reference():
    content = _read("testing_guide.md").lower()
    has_io_mock = "io mock" in content
    has_io_boundaries = "io boundaries" in content
    assert has_io_mock or has_io_boundaries, (
        "testing_guide.md missing IO mock reference "
        "(expected 'IO mock' or 'IO boundaries')"
    )


# --- secret pattern check ---

def test_no_worker_prompt_contains_hardcoded_secrets():
    pattern = re.compile(
        r"(key|token|secret|password)\s*=\s*['\"][^'\"]{8,}",
        re.IGNORECASE,
    )
    for f in PROMPT_FILES:
        content = _read(f)
        matches = pattern.findall(content)
        assert not matches, (
            f"{f} contains potential hardcoded secret pattern: {matches}"
        )
