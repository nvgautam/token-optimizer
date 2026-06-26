# tests/prompts/test_oracle_prompts.py
import re
from pathlib import Path

ORACLE_DIR = Path("commands/oracle")

# Test 1: all files valid UTF-8
def test_all_oracle_prompt_files_valid_utf8():
    for f in ["checklist.md", "market.md", "generation.md"]:
        (ORACLE_DIR / f).read_text(encoding="utf-8")  # raises if not valid UTF-8

# Test 2: no file exceeds 150 lines
def test_no_oracle_prompt_file_exceeds_150_lines():
    for f in ["checklist.md", "market.md", "generation.md"]:
        lines = (ORACLE_DIR / f).read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 150, f"{f} has {len(lines)} lines (max 150)"

# Test 3: checklist.md has >= 23 ## section headers
def test_checklist_md_has_23_plus_section_headers():
    content = (ORACLE_DIR / "checklist.md").read_text(encoding="utf-8")
    headers = re.findall(r'^## .+', content, re.MULTILINE)
    assert len(headers) >= 23, f"Only {len(headers)} ## headers found (need >= 23)"

# Test 4: market.md contains all three segment sections
def test_market_md_contains_all_three_segments():
    content = (ORACLE_DIR / "market.md").read_text(encoding="utf-8")
    for segment in ["## Consumer", "## SMB", "## Enterprise"]:
        assert segment in content, f"Missing segment section: {segment}"

# Test 5: market.md contains compliance defaults per segment
def test_market_md_contains_compliance_defaults():
    content = (ORACLE_DIR / "market.md").read_text(encoding="utf-8").lower()
    assert "gdpr" in content, "market.md missing GDPR reference"
    assert "soc2" in content or "soc 2" in content, "market.md missing SOC2 reference"

# Test 6: generation.md contains RESOLVED/UNRESOLVED/DEFERRED format
def test_generation_md_contains_status_format():
    content = (ORACLE_DIR / "generation.md").read_text(encoding="utf-8")
    for status in ["RESOLVED", "UNRESOLVED", "DEFERRED"]:
        assert status in content, f"generation.md missing status: {status}"

# Test 7: generation.md contains compact writing rule
def test_generation_md_contains_compact_writing_rule():
    content = (ORACLE_DIR / "generation.md").read_text(encoding="utf-8").lower()
    assert "table" in content or "bullet" in content, "generation.md missing compact writing rule"
    assert "prose" in content, "generation.md should explicitly forbid prose paragraphs"

# Test 8: checklist.md contains prompt injection NFR
def test_checklist_md_contains_prompt_injection_nfr():
    content = (ORACLE_DIR / "checklist.md").read_text(encoding="utf-8").lower()
    assert "prompt injection" in content or "untrusted input" in content, \
        "checklist.md missing prompt injection / untrusted input section"

# Test 9: no hardcoded secrets in any file
def test_no_hardcoded_secrets_in_oracle_prompts():
    secret_pattern = re.compile(r'(password|api_key|secret)\s*=\s*["\'][^"\']{8,}', re.IGNORECASE)
    for f in ["checklist.md", "market.md", "generation.md"]:
        content = (ORACLE_DIR / f).read_text(encoding="utf-8")
        assert not secret_pattern.search(content), f"Possible hardcoded secret in {f}"
