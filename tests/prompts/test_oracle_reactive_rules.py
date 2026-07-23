# tests/prompts/test_oracle_reactive_rules.py
"""Tests for Reactive Re-prioritization rules in oracle skills."""
import re
from pathlib import Path

ORACLE_FILES = [
    Path("commands/claude/oracle.md"),
    Path("commands/gemini/skills/oracle/SKILL.md"),
]


# Test 1: Reactive Re-prioritization section exists
def test_reactive_reprioritization_section_exists():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        assert "Reactive Re-prioritization" in content, \
            f"{f.name} must contain 'Reactive Re-prioritization' section"


# Test 2: Reactive Re-prioritization lazy-loads prioritization.md on trigger
def test_reactive_reprioritization_lazy_loads_prioritization():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        # Find the Reactive Re-prioritization section
        reactive_section = re.search(
            r"### Reactive Re-prioritization\s*\n\n(.*?)(?=\n### |\Z)",
            content,
            re.DOTALL | re.MULTILINE
        )
        assert reactive_section, \
            f"{f.name} must have Reactive Re-prioritization section with content"

        section_content = reactive_section.group(1)
        # Must mention lazy-loading prioritization.md
        assert "prioritization.md" in section_content.lower() or "lazy load" in section_content.lower(), \
            f"{f.name} Reactive Re-prioritization section must lazy-load prioritization.md"


# Test 3: Reactive Re-prioritization enforces pairwise-disjoint OWNS checks
def test_reactive_reprioritization_enforces_disjoint_owns_checks():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        # Find the Reactive Re-prioritization section
        reactive_section = re.search(
            r"### Reactive Re-prioritization\s*\n\n(.*?)(?=\n### |\Z)",
            content,
            re.DOTALL | re.MULTILINE
        )
        assert reactive_section, f"{f.name} must have Reactive Re-prioritization section"

        section_content = reactive_section.group(1)
        # Must mention disjoint, pairwise, or OWNS checks
        disjoint_check = "disjoint" in section_content.lower() or \
                         "pairwise" in section_content.lower() or \
                         "owns" in section_content.lower()
        assert disjoint_check, \
            f"{f.name} Reactive Re-prioritization must enforce disjoint OWNS checks for parallel tasks"


# Test 4: Reactive Re-prioritization includes tool-blocking sequence
def test_reactive_reprioritization_tool_blocking_prevents_writes():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        # Find the Reactive Re-prioritization section
        reactive_section = re.search(
            r"### Reactive Re-prioritization\s*\n\n(.*?)(?=\n### |\Z)",
            content,
            re.DOTALL | re.MULTILINE
        )
        assert reactive_section, f"{f.name} must have Reactive Re-prioritization section"

        section_content = reactive_section.group(1)
        # Must prevent writes until user confirms (mentions confirmation, no write, block, etc.)
        block_check = re.search(
            r"block.*write|no.*write.*until|confirm.*before|prevent.*write|lock|do not write",
            section_content,
            re.IGNORECASE
        )
        assert block_check, \
            f"{f.name} Reactive Re-prioritization must include tool-blocking sequence preventing writes until confirmation"


# Test 5: Reactive Re-prioritization mentions execution_plan.md or tasks.json
def test_reactive_reprioritization_mentions_protected_files():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        # Find the Reactive Re-prioritization section
        reactive_section = re.search(
            r"### Reactive Re-prioritization\s*\n\n(.*?)(?=\n### |\Z)",
            content,
            re.DOTALL | re.MULTILINE
        )
        assert reactive_section, f"{f.name} must have Reactive Re-prioritization section"

        section_content = reactive_section.group(1)
        # Must mention execution_plan.md or tasks.json (the protected files)
        protected_files = "execution_plan.md" in section_content or "tasks.json" in section_content
        assert protected_files, \
            f"{f.name} Reactive Re-prioritization must reference execution_plan.md or tasks.json"


# Test 6: Reactive Re-prioritization mentions user confirmation
def test_reactive_reprioritization_requires_user_confirmation():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        # Find the Reactive Re-prioritization section
        reactive_section = re.search(
            r"### Reactive Re-prioritization\s*\n\n(.*?)(?=\n### |\Z)",
            content,
            re.DOTALL | re.MULTILINE
        )
        assert reactive_section, f"{f.name} must have Reactive Re-prioritization section"

        section_content = reactive_section.group(1)
        # Must mention user confirmation (confirm, approve, agree, etc.)
        confirmation = re.search(
            r"confirm|approve|agree|user.*accept|explicit.*confirm",
            section_content,
            re.IGNORECASE
        )
        assert confirmation, \
            f"{f.name} Reactive Re-prioritization must require explicit user confirmation before writing files"


# Test 7: Anti-Bias & Critical Analysis block exists in Phase 2
def test_anti_bias_critical_analysis_exists():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        assert "Anti-Bias & Critical Analysis" in content, \
            f"{f.name} must contain 'Anti-Bias & Critical Analysis' rules"
        assert "Anti-Anchoring" in content, \
            f"{f.name} must contain 'Anti-Anchoring' term"

