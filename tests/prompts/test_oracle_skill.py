# tests/prompts/test_oracle_skill.py
"""Tests for commands/oracle.md — the Claude oracle skill."""
import re
from pathlib import Path

ORACLE_SKILL = Path("commands/oracle.md")


def _content() -> str:
    return ORACLE_SKILL.read_text(encoding="utf-8")


# Test 1: architecture.md UNRESOLVED check on startup
def test_oracle_skill_checks_architecture_unresolved_on_startup():
    content = _content()
    # Must mention reading architecture.md and checking for UNRESOLVED items
    assert "architecture.md" in content, "oracle.md must reference architecture.md"
    assert "UNRESOLVED" in content, "oracle.md must check for UNRESOLVED items"
    # The check must appear in the startup section, not only in later phases
    startup_section = content.split("## Phase")[0]
    assert "architecture.md" in startup_section, \
        "architecture.md UNRESOLVED check must appear before Phase 1"
    assert "UNRESOLVED" in startup_section, \
        "UNRESOLVED keyword must appear in startup section"


# Test 2: multi-persona declaration (PE + PM + Designer)
def test_oracle_skill_declares_three_personas():
    content = _content()
    # All three personas must appear
    for persona in ["Principal Engineer", "Principal PM", "Principal Designer"]:
        assert persona in content or persona.replace("Principal ", "PE").replace("Principal ", "PM") in content, \
            f"oracle.md must declare persona: {persona}"
    # Specifically check that all three are present (PE, PM, Designer)
    assert re.search(r"Engineer", content), "PE persona missing"
    assert re.search(r"PM|Product Manager", content), "PM persona missing"
    assert re.search(r"Designer", content), "Designer persona missing"
    # Must be declared together (same line or block)
    lines = content.splitlines()
    persona_lines = [l for l in lines if "Engineer" in l and ("PM" in l or "Product" in l) and "Designer" in l]
    assert persona_lines, \
        "oracle.md must declare all three personas (Engineer, PM, Designer) on the same line or block"


# Test 3: no hardcoded project-specific content
def test_oracle_skill_contains_no_specific_project_names():
    content = _content()
    # Should not reference specific project names from the AgentFlow project
    forbidden = ["AgentFlow", "token-optimizer", "PTY shell", "tiktoken", "agentflow/shell"]
    for term in forbidden:
        assert term not in content, \
            f"oracle.md must be generic — found project-specific term: '{term}'"


# Test 4: ~2% budget announcement
def test_oracle_skill_contains_budget_announcement():
    content = _content()
    # Must announce ~2% of 5-hour window usage
    assert "2%" in content, "oracle.md must announce ~2% of window usage"
    assert "5-hour" in content or "5 hour" in content, \
        "oracle.md must reference the 5-hour window"
    # The announcement must come early (startup section)
    idx_2pct = content.find("2%")
    idx_first_phase = content.find("## Phase")
    assert idx_2pct < idx_first_phase, \
        "Budget announcement must appear before Phase 1"


# Test 5: ≤3-sentence verbosity rule for spar phase
def test_oracle_skill_contains_three_sentence_verbosity_rule():
    content = _content()
    # Must specify ≤3 sentences per exchange
    assert re.search(r"≤\s*3\s*sentence|3\s*sentence|three\s*sentence", content, re.IGNORECASE), \
        "oracle.md must specify ≤3 sentences per exchange verbosity rule"
    # Must appear in the sparring/checklist phase, not just generation
    phase2_match = re.search(r"## Phase 2.*?## Phase 3", content, re.DOTALL)
    assert phase2_match, "oracle.md must have Phase 2 and Phase 3 sections"
    phase2_content = phase2_match.group(0)
    assert re.search(r"≤\s*3\s*sentence|3\s*sentence|three\s*sentence", phase2_content, re.IGNORECASE), \
        "Verbosity rule must appear in the sparring phase (Phase 2)"


# Test 6: lazy sub-file loading (per phase, not at startup)
def test_oracle_skill_uses_lazy_subfile_loading():
    content = _content()
    # market.md, checklist.md, and generation.md must NOT all be loaded at startup
    startup_section = content.split("## Phase")[0]
    # Startup should only mention architecture.md (for UNRESOLVED check)
    # market.md, checklist.md, and generation.md should appear in their respective phases
    for sub_file in ["market.md", "checklist.md", "generation.md"]:
        assert sub_file not in startup_section, \
            f"{sub_file} must NOT be loaded at startup — lazy load only in its phase"

    # Each sub-file must appear in its respective phase section
    assert "market.md" in content, "market.md must be referenced (lazily, in market phase)"
    assert "checklist.md" in content, "checklist.md must be referenced (lazily, in checklist phase)"
    assert "generation.md" in content, "generation.md must be referenced (lazily, in generation phase)"

    # Lazy load instruction must indicate per-phase loading
    assert re.search(r"[Ll]azy\s+load|only when entering|not at startup", content), \
        "oracle.md must contain lazy loading instruction (e.g. 'Lazy load' or 'only when entering')"
