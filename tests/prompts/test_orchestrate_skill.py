# tests/prompts/test_orchestrate_skill.py
"""Tests for orchestrate skills (Claude Code and agy SKILL.md equivalents)."""
import re
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
CLAUDE_ORCHESTRATE = REPO / "commands" / "orchestrate.md"
AGY_ORCHESTRATE = REPO / ".agents" / "skills" / "orchestrate" / "SKILL.md"


def test_orchestrate_skills_exist():
    assert CLAUDE_ORCHESTRATE.exists(), "commands/orchestrate.md must exist"
    assert AGY_ORCHESTRATE.exists(), ".agents/skills/orchestrate/SKILL.md must exist"


def test_agy_orchestrate_has_yaml_frontmatter():
    content = AGY_ORCHESTRATE.read_text(encoding="utf-8")
    assert content.startswith("---"), "AGY SKILL.md must start with YAML frontmatter delimiter"
    # Find frontmatter
    parts = content.split("---")
    assert len(parts) >= 3, "AGY SKILL.md must have both start and end frontmatter delimiters"
    frontmatter = parts[1]
    assert "name: orchestrate" in frontmatter, "AGY SKILL.md must declare name: orchestrate"
    assert "description:" in frontmatter, "AGY SKILL.md must declare description"


def test_orchestrate_skills_contain_oracle_complete_gate():
    for f in [CLAUDE_ORCHESTRATE, AGY_ORCHESTRATE]:
        content = f.read_text(encoding="utf-8")
        assert "design_status.md" in content, f"{f.name} must check design_status.md"
        assert "UNRESOLVED" in content, f"{f.name} must stop on UNRESOLVED items"


def test_orchestrate_skills_contain_round_sizing_heuristic():
    for f in [CLAUDE_ORCHESTRATE, AGY_ORCHESTRATE]:
        content = f.read_text(encoding="utf-8")
        assert "round-sizing" in content.lower() or "round-sizing heuristic" in content.lower() or "round sizing" in content.lower(), \
            f"{f.name} must contain the round-sizing heuristic section"
        assert "orchestrator_threshold_tokens" in content, \
            f"{f.name} must reference orchestrator_threshold_tokens in round-sizing"


def test_orchestrate_skills_contain_rate_pacing_protocol():
    for f in [CLAUDE_ORCHESTRATE, AGY_ORCHESTRATE]:
        content = f.read_text(encoding="utf-8")
        assert "rate-pacing" in content.lower() or "rate pacing" in content.lower(), \
            f"{f.name} must contain rate pacing protocol"
        assert "alone" in content.lower(), f"{f.name} must spawn first agent alone"
        assert "3 × pct_cost" in content or "3x pct_cost" in content.lower() or "3 * pct_cost" in content, \
            f"{f.name} must check remaining budget against 3x pct_cost"


def test_orchestrate_skills_contain_prompt_assembly_rules():
    for f in [CLAUDE_ORCHESTRATE, AGY_ORCHESTRATE]:
        content = f.read_text(encoding="utf-8")
        # Worker prompt components to embed
        assert "commands/worker/system.md" in content, f"{f.name} must embed worker system prompt"
        assert "commands/worker/context_bundle.md" in content, f"{f.name} must embed context bundle format"
        assert "commands/worker/testing_guide.md" in content, f"{f.name} must embed testing guide"
        assert "TOKENS: input=N output=N" in content, f"{f.name} must require workers to end with TOKENS: input=N output=N"


def test_no_hardcoded_secrets_in_orchestrate():
    secret_pattern = re.compile(r'(password|api_key|secret)\s*=\s*["\'][^"\']{8,}', re.IGNORECASE)
    for f in [CLAUDE_ORCHESTRATE, AGY_ORCHESTRATE]:
        content = f.read_text(encoding="utf-8")
        assert not secret_pattern.search(content), f"{f.name} contains a possible hardcoded secret"
