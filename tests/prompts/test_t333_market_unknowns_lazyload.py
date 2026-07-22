# tests/prompts/test_t333_market_unknowns_lazyload.py
"""T-333: oracle.md + Gemini SKILL.md — market_unknowns.md lazy-load in Phase 1 emit block."""
import re
from pathlib import Path

ORACLE_FILES = [
    Path("commands/claude/oracle.md"),
    Path("commands/gemini/skills/oracle/SKILL.md"),
]
MARKET_UNKNOWNS_FILE = Path("commands/claude/oracle/market_unknowns.md")


# Test 1: market_unknowns.md file exists and is valid UTF-8
def test_market_unknowns_file_exists():
    assert MARKET_UNKNOWNS_FILE.exists(), "commands/claude/oracle/market_unknowns.md must exist"
    MARKET_UNKNOWNS_FILE.read_text(encoding="utf-8")  # raises if not valid UTF-8


# Test 2: market_unknowns.md has all four segment sections
def test_market_unknowns_has_segment_sections():
    content = MARKET_UNKNOWNS_FILE.read_text(encoding="utf-8")
    for segment in ["## B2C", "## SMB", "## Enterprise", "## Developer"]:
        assert segment in content, f"market_unknowns.md missing segment section: {segment}"


# Test 3: market_unknowns.md is NOT loaded at startup in either skill
def test_market_unknowns_not_loaded_at_startup():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        startup_section = content.split("## Phase")[0]
        assert "market_unknowns" not in startup_section, (
            f"market_unknowns.md must NOT be loaded at startup in {f.name} — "
            "lazy load only after segment resolves"
        )


# Test 4: oracle.md Phase 1 block references market_unknowns.md
def test_oracle_md_phase1_references_market_unknowns():
    content = Path("commands/claude/oracle.md").read_text(encoding="utf-8")
    phase1_match = re.search(r"## Phase 1.*?(?=## Phase 2)", content, re.DOTALL)
    assert phase1_match, "oracle.md must have a Phase 1 section"
    phase1 = phase1_match.group(0)
    assert "market_unknowns" in phase1, (
        "oracle.md Phase 1 must lazy-load commands/claude/oracle/market_unknowns.md"
    )


# Test 5: Gemini SKILL.md Phase 1 block references market_unknowns.md
def test_gemini_skill_phase1_references_market_unknowns():
    content = Path("commands/gemini/skills/oracle/SKILL.md").read_text(encoding="utf-8")
    phase1_match = re.search(r"## Phase 1.*?(?=## Phase 2)", content, re.DOTALL)
    assert phase1_match, "Gemini SKILL.md must have a Phase 1 section"
    phase1 = phase1_match.group(0)
    assert "market_unknowns" in phase1, (
        "Gemini SKILL.md Phase 1 must lazy-load commands/claude/oracle/market_unknowns.md"
    )


# Test 6: lazy-load instruction appears after the segment-resolution Emit line
def test_market_unknowns_lazyload_follows_emit_in_phase1():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        phase1_match = re.search(r"## Phase 1.*?(?=## Phase 2)", content, re.DOTALL)
        assert phase1_match, f"{f.name} must have a Phase 1 section"
        phase1 = phase1_match.group(0)
        emit_idx = phase1.find("HANDOFF RECOMMENDED")
        unknowns_idx = phase1.find("market_unknowns")
        assert emit_idx != -1, f"{f.name} Phase 1 must contain the HANDOFF RECOMMENDED emit line"
        assert unknowns_idx != -1, f"{f.name} Phase 1 must reference market_unknowns"
        assert unknowns_idx > emit_idx, (
            f"{f.name}: market_unknowns lazy-load must come after the HANDOFF RECOMMENDED emit"
        )


# Test 7: lazy-load instruction uses 'Lazy load' marker (matching the pattern elsewhere)
def test_market_unknowns_uses_lazy_load_marker():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        phase1_match = re.search(r"## Phase 1.*?(?=## Phase 2)", content, re.DOTALL)
        assert phase1_match, f"{f.name} must have Phase 1"
        phase1 = phase1_match.group(0)
        assert re.search(r"\*\*Lazy load:?\*\*.*market_unknowns", phase1), (
            f"{f.name} Phase 1: market_unknowns must be introduced with a '**Lazy load:**' marker"
        )


# Test 8: instruction says to surface 2–3 questions matching the resolved segment
def test_market_unknowns_instructs_surface_2_3_questions():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        phase1_match = re.search(r"## Phase 1.*?(?=## Phase 2)", content, re.DOTALL)
        assert phase1_match, f"{f.name} must have Phase 1"
        phase1 = phase1_match.group(0)
        # Must direct the model to surface questions, not just load the file
        assert re.search(
            r"2.3\s+question|2\s*[–-]\s*3\s+question|surface.*question|question.*segment",
            phase1,
            re.IGNORECASE,
        ), (
            f"{f.name} Phase 1 must instruct surfacing 2–3 questions matching the resolved segment"
        )


# Test 9: oracle.md file size stays ≤ 150 lines
def test_oracle_md_within_150_lines():
    content = Path("commands/claude/oracle.md").read_text(encoding="utf-8")
    lines = content.splitlines()
    assert len(lines) <= 150, f"commands/claude/oracle.md has {len(lines)} lines (max 150)"


# Test 10: Gemini SKILL.md file size stays ≤ 150 lines
def test_gemini_skill_within_150_lines():
    content = Path("commands/gemini/skills/oracle/SKILL.md").read_text(encoding="utf-8")
    lines = content.splitlines()
    assert len(lines) <= 150, f"Gemini SKILL.md has {len(lines)} lines (max 150)"
