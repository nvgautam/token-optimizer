"""Content-assertion tests for CLAUDE.md Reading protocol section (T-038)."""

from pathlib import Path

CLAUDE_MD = Path(__file__).parents[2] / "CLAUDE.md"


def _content() -> str:
    return CLAUDE_MD.read_text()


def test_reading_protocol_section_exists():
    assert "## Reading protocol" in _content()


def test_reading_protocol_idx_path():
    content = _content()
    assert "sha256" in content
    assert ".idx" in content


def test_reading_protocol_offset_syntax():
    content = _content()
    assert "offset=start" in content
    assert "limit=end-start+1" in content


def test_reading_protocol_fallback():
    content = _content()
    # The section must document what to do when .idx is absent
    assert "fallback" in content.lower() or "absent" in content.lower()


def test_reading_protocol_absence_explanation():
    content = _content()
    assert "< 50 lines" in content or "not yet indexed" in content
