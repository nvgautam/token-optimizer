"""Tests for T-353: Coding Standards Compliance check in code_review.md."""
from __future__ import annotations
from pathlib import Path


class TestCodingStandardsComplianceSection:
    """T-353: code_review.md must include Coding Standards Compliance check section."""

    def test_code_review_has_coding_standards_section(self):
        """code_review.md must contain a Coding Standards Compliance section."""
        code_review_path = Path(__file__).parent.parent / "commands/claude/reviewer/code_review.md"
        content = code_review_path.read_text()
        assert "Coding Standards Compliance" in content, \
            "code_review.md must have a Coding Standards Compliance section"

    def test_coding_standards_section_references_standards_file(self):
        """The Coding Standards Compliance section must reference coding_standards.md."""
        code_review_path = Path(__file__).parent.parent / "commands/claude/reviewer/code_review.md"
        content = code_review_path.read_text()
        assert "coding_standards.md" in content, \
            "Coding Standards Compliance section must reference coding_standards.md"

    def test_coding_standards_section_mentions_lazy_loading(self):
        """The section must describe lazy-loading the coding_standards.md file."""
        code_review_path = Path(__file__).parent.parent / "commands/claude/reviewer/code_review.md"
        content = code_review_path.read_text()
        # Check that section exists and mentions loading the standards
        assert "Coding Standards Compliance" in content, "Section missing"
        # Verify that the section comes before the Output Format section
        standards_idx = content.find("Coding Standards Compliance")
        output_idx = content.find("## Output Format")
        assert standards_idx > 0, "Coding Standards Compliance section not found"
        assert standards_idx < output_idx, "Coding Standards Compliance section must come before Output Format"

    def test_coding_standards_section_flags_hardcoded_strings(self):
        """The section must describe flagging hardcoded strings."""
        code_review_path = Path(__file__).parent.parent / "commands/claude/reviewer/code_review.md"
        content = code_review_path.read_text()
        # Get the Coding Standards Compliance section
        standards_start = content.find("Coding Standards Compliance")
        assert standards_start > 0, "Section not found"
        section_end = content.find("## Output Format", standards_start)
        section_content = content[standards_start:section_end]
        # Check for mention of hardcoded strings or constants
        assert any(kw in section_content.lower() for kw in ["hardcoded", "string", "constant"]), \
            "Section must address hardcoded strings"

    def test_coding_standards_section_flags_bare_except(self):
        """The section must describe handling bare except statements."""
        code_review_path = Path(__file__).parent.parent / "commands/claude/reviewer/code_review.md"
        content = code_review_path.read_text()
        standards_start = content.find("Coding Standards Compliance")
        assert standards_start > 0, "Section not found"
        section_end = content.find("## Output Format", standards_start)
        section_content = content[standards_start:section_end]
        # Check for mention of bare except
        assert any(kw in section_content.lower() for kw in ["bare except", "exception"]), \
            "Section must address exception handling"

    def test_coding_standards_section_flags_file_size_violations(self):
        """The section must describe checking file size limits."""
        code_review_path = Path(__file__).parent.parent / "commands/claude/reviewer/code_review.md"
        content = code_review_path.read_text()
        standards_start = content.find("Coding Standards Compliance")
        assert standards_start > 0, "Section not found"
        section_end = content.find("## Output Format", standards_start)
        section_content = content[standards_start:section_end]
        # Check for mention of file sizes or line limits
        assert any(kw in section_content.lower() for kw in ["file", "line", "size", "limit"]), \
            "Section must address file size limits"
