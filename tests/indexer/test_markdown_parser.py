"""Tests for agentflow.indexer.parsers.markdown_parser."""
from __future__ import annotations

from pathlib import Path

import pytest

from agentflow.indexer import IndexEntry
from agentflow.indexer.parsers.markdown_parser import parse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _write_md(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "sample.md"
    p.write_text(content, encoding="utf-8")
    return p


def _long_content(extra: str = "") -> str:
    """Return markdown content that is >= 50 lines."""
    # 10-line preamble before any headers
    preamble = "\n".join([f"line {i}" for i in range(1, 11)]) + "\n"
    body = (
        "## Section One\n"
        + "\n".join([f"content {i}" for i in range(12)]) + "\n"
        + "### Sub-section A\n"
        + "\n".join([f"sub content {i}" for i in range(10)]) + "\n"
        + "## Section Two\n"
        + "\n".join([f"more content {i}" for i in range(10)]) + "\n"
    )
    combined = preamble + body + extra
    # Pad to ensure >= 50 lines
    lines = combined.splitlines()
    while len(lines) < 50:
        lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Scenario 1: H2 headers extracted with correct name and start_line
# ---------------------------------------------------------------------------

class TestH2Headers:
    def test_h2_name_includes_prefix(self, tmp_path: Path) -> None:
        content = _long_content()
        path = _write_md(tmp_path, content)
        entries = parse(path)
        h2_names = [e.name for e in entries if e.name.startswith("## ")]
        assert "## Section One" in h2_names

    def test_h2_start_line_is_correct(self, tmp_path: Path) -> None:
        content = _long_content()
        lines = content.splitlines()
        path = _write_md(tmp_path, content)
        entries = parse(path)
        # Find the actual line number of "## Section One"
        expected_line = next(
            i + 1 for i, l in enumerate(lines) if l == "## Section One"
        )
        match = next(e for e in entries if e.name == "## Section One")
        assert match.start_line == expected_line


# ---------------------------------------------------------------------------
# Scenario 2: H3 headers extracted with correct name and start_line
# ---------------------------------------------------------------------------

class TestH3Headers:
    def test_h3_name_includes_prefix(self, tmp_path: Path) -> None:
        content = _long_content()
        path = _write_md(tmp_path, content)
        entries = parse(path)
        h3_names = [e.name for e in entries if e.name.startswith("### ")]
        assert "### Sub-section A" in h3_names

    def test_h3_start_line_is_correct(self, tmp_path: Path) -> None:
        content = _long_content()
        lines = content.splitlines()
        path = _write_md(tmp_path, content)
        entries = parse(path)
        expected_line = next(
            i + 1 for i, l in enumerate(lines) if l == "### Sub-section A"
        )
        match = next(e for e in entries if e.name == "### Sub-section A")
        assert match.start_line == expected_line


# ---------------------------------------------------------------------------
# Scenario 3: end_line spans to line before next header of same/higher level
# ---------------------------------------------------------------------------

class TestEndLineBoundaries:
    def test_h2_ends_before_next_h2(self, tmp_path: Path) -> None:
        content = _long_content()
        lines = content.splitlines()
        path = _write_md(tmp_path, content)
        entries = parse(path)

        section_one = next(e for e in entries if e.name == "## Section One")
        section_two_start = next(
            i + 1 for i, l in enumerate(lines) if l == "## Section Two"
        )
        assert section_one.end_line == section_two_start - 1

    def test_h3_ends_before_next_h2(self, tmp_path: Path) -> None:
        content = _long_content()
        lines = content.splitlines()
        path = _write_md(tmp_path, content)
        entries = parse(path)

        sub_a = next(e for e in entries if e.name == "### Sub-section A")
        section_two_start = next(
            i + 1 for i, l in enumerate(lines) if l == "## Section Two"
        )
        # H3 should end before the next H2 (higher level closes H3 too)
        assert sub_a.end_line == section_two_start - 1

    def test_h3_ends_before_next_h3_of_same_parent(self, tmp_path: Path) -> None:
        """Two H3s under the same H2 — first H3 ends before second H3."""
        base = "\n".join([f"line {i}" for i in range(20)])
        content = (
            base + "\n"
            "## Parent\n"
            + "\n".join([f"p {i}" for i in range(5)]) + "\n"
            "### Child One\n"
            "child one content\n"
            "more child one\n"
            "### Child Two\n"
            "child two content\n"
        )
        lines = content.splitlines()
        while len(lines) < 50:
            lines.append("")
        content = "\n".join(lines) + "\n"
        path = _write_md(tmp_path, content)
        entries = parse(path)

        child_one = next(e for e in entries if e.name == "### Child One")
        child_two_start = next(
            i + 1 for i, l in enumerate(lines) if l == "### Child Two"
        )
        assert child_one.end_line == child_two_start - 1


# ---------------------------------------------------------------------------
# Scenario 4: last section end_line is EOF (last line number)
# ---------------------------------------------------------------------------

class TestLastSectionEOF:
    def test_last_section_end_line_is_eof(self, tmp_path: Path) -> None:
        content = _long_content()
        lines = content.splitlines()
        path = _write_md(tmp_path, content)
        entries = parse(path)
        last_entry = max(entries, key=lambda e: e.start_line)
        assert last_entry.end_line == len(lines)


# ---------------------------------------------------------------------------
# Scenario 5 & 6: short and empty files return []
# ---------------------------------------------------------------------------

class TestShortFiles:
    def test_file_with_fewer_than_50_lines_returns_empty(self, tmp_path: Path) -> None:
        content = "## Header\nsome content\n"
        path = _write_md(tmp_path, content)
        assert parse(path) == []

    def test_empty_file_returns_empty(self, tmp_path: Path) -> None:
        path = _write_md(tmp_path, "")
        assert parse(path) == []

    def test_exactly_49_lines_returns_empty(self, tmp_path: Path) -> None:
        content = "\n".join(["x"] * 49) + "\n"
        # 49 lines
        path = _write_md(tmp_path, content)
        assert parse(path) == []

    def test_exactly_50_lines_not_empty_when_has_headers(self, tmp_path: Path) -> None:
        # Build a file with exactly 50 lines including at least one header.
        # "\n".join(50 items) + "\n" → splitlines() produces exactly 50 lines.
        lines = ["x"] * 50
        lines[5] = "## My Header"
        content = "\n".join(lines) + "\n"
        path = _write_md(tmp_path, content)
        result = parse(path)
        assert any(e.name == "## My Header" for e in result)


# ---------------------------------------------------------------------------
# Scenario 7: unreadable file returns [] without raising
# ---------------------------------------------------------------------------

class TestUnreadableFile:
    def test_nonexistent_file_returns_empty(self) -> None:
        result = parse(Path("/nonexistent/no/such/file.md"))
        assert result == []

    def test_no_exception_raised_for_bad_path(self) -> None:
        try:
            result = parse(Path("/nonexistent/no/such/file.md"))
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"parse() raised an exception: {exc}")


# ---------------------------------------------------------------------------
# Scenario 8: kind field is 'section' for all entries
# ---------------------------------------------------------------------------

class TestKindField:
    def test_all_entries_have_kind_section(self, tmp_path: Path) -> None:
        content = _long_content()
        path = _write_md(tmp_path, content)
        entries = parse(path)
        assert entries, "Expected at least one entry"
        for entry in entries:
            assert entry.kind == "section"


# ---------------------------------------------------------------------------
# Scenario 9: signature field is None for all entries
# ---------------------------------------------------------------------------

class TestSignatureField:
    def test_all_entries_have_no_signature(self, tmp_path: Path) -> None:
        content = _long_content()
        path = _write_md(tmp_path, content)
        entries = parse(path)
        assert entries, "Expected at least one entry"
        for entry in entries:
            assert entry.signature is None


# ---------------------------------------------------------------------------
# Additional: H4+ headers are NOT extracted
# ---------------------------------------------------------------------------

class TestH4NotExtracted:
    def test_h4_headers_are_skipped(self, tmp_path: Path) -> None:
        base = "\n".join([f"line {i}" for i in range(20)])
        content = (
            base + "\n"
            "## Top\n"
            + "\n".join([f"t {i}" for i in range(15)]) + "\n"
            "#### Deep Header\n"
            + "\n".join([f"d {i}" for i in range(10)]) + "\n"
        )
        lines = content.splitlines()
        while len(lines) < 50:
            lines.append("")
        content = "\n".join(lines) + "\n"
        path = _write_md(tmp_path, content)
        entries = parse(path)
        names = [e.name for e in entries]
        assert not any("####" in n for n in names)
