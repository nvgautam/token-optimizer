# tests/prompts/test_orchestrate_skill.py
"""Tests for orchestrate skills (Claude Code and agy SKILL.md equivalents)."""
import re
import pytest
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
CLAUDE_ORCHESTRATE = REPO / "commands" / "claude" / "orchestrate.md"
GEMINI_ORCHESTRATE = REPO / "commands" / "gemini" / "skills" / "orchestrate" / "SKILL.md"
AGY_ORCHESTRATE = REPO / ".agents" / "skills" / "orchestrate" / "SKILL.md"

# Only include files that exist — AGY SKILL.md is optional (created separately)
SKILL_FILES = [f for f in [CLAUDE_ORCHESTRATE, GEMINI_ORCHESTRATE, AGY_ORCHESTRATE] if f.exists()]


def test_orchestrate_skills_exist():
    assert CLAUDE_ORCHESTRATE.exists(), "commands/orchestrate.md must exist"


@pytest.mark.skipif(not AGY_ORCHESTRATE.exists(), reason="AGY SKILL.md not yet created")
def test_agy_orchestrate_has_yaml_frontmatter():
    content = AGY_ORCHESTRATE.read_text(encoding="utf-8")
    assert content.startswith("---"), "AGY SKILL.md must start with YAML frontmatter delimiter"
    parts = content.split("---")
    assert len(parts) >= 3, "AGY SKILL.md must have both start and end frontmatter delimiters"
    frontmatter = parts[1]
    assert "name: orchestrate" in frontmatter, "AGY SKILL.md must declare name: orchestrate"
    assert "description:" in frontmatter, "AGY SKILL.md must declare description"


def test_orchestrate_skills_contain_oracle_complete_gate():
    for f in SKILL_FILES:
        content = f.read_text(encoding="utf-8")
        assert "design_status.md" in content, f"{f.name} must check design_status.md"
        assert "UNRESOLVED" in content, f"{f.name} must stop on UNRESOLVED items"


def test_orchestrate_skills_contain_round_sizing_heuristic():
    for f in SKILL_FILES:
        content = f.read_text(encoding="utf-8")
        assert (
            "round-sizing" in content.lower()
            or "round-sizing heuristic" in content.lower()
            or "round sizing" in content.lower()
        ), f"{f.name} must contain the round-sizing heuristic section"
        assert "orchestrator_threshold_tokens" in content, \
            f"{f.name} must reference orchestrator_threshold_tokens in round-sizing"


def test_orchestrate_skills_contain_rate_pacing_protocol():
    for f in SKILL_FILES:
        content = f.read_text(encoding="utf-8")
        assert "rate-pacing" in content.lower() or "rate pacing" in content.lower(), \
            f"{f.name} must contain rate pacing protocol"
        assert "alone" in content.lower(), f"{f.name} must spawn first agent alone"
        assert (
            "3 × pct_cost" in content
            or "3x pct_cost" in content.lower()
            or "3 * pct_cost" in content
        ), f"{f.name} must check remaining budget against 3x pct_cost"


def test_orchestrate_skills_contain_prompt_assembly_rules():
    for f in SKILL_FILES:
        content = f.read_text(encoding="utf-8")
        assert "worker/system.md" in content, f"{f.name} must embed worker system prompt"
        assert "worker/context_bundle.md" in content, f"{f.name} must embed context bundle format"
        assert "worker/testing_guide.md" in content, f"{f.name} must embed testing guide"
        assert "TOKENS: input=N output=N" in content, f"{f.name} must require workers to end with TOKENS: input=N output=N"


def test_no_hardcoded_secrets_in_orchestrate():
    secret_pattern = re.compile(r'(password|api_key|secret)\s*=\s*["\'][^"\']{8,}', re.IGNORECASE)
    for f in SKILL_FILES:
        content = f.read_text(encoding="utf-8")
        assert not secret_pattern.search(content), f"{f.name} contains a possible hardcoded secret"


# T-033: Variance-aware scheduling tests

def test_orchestrate_tracks_observed_task_costs():
    """T-033: orchestrate.md tracks observed task costs from TOKENS: reports."""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    assert "observed_costs" in content or "observed_cost" in content.lower(), \
        "orchestrate.md must track observed task costs in observed_costs[]"
    assert "TOKENS:" in content, \
        "orchestrate.md must reference TOKENS: report for cost tracking"


def test_orchestrate_uses_static_default_when_sample_count_low():
    """T-033: orchestrate.md uses static 2500 default when sample_count < 7."""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    assert "sample_count" in content, \
        "orchestrate.md must reference sample_count"
    assert "2500" in content, \
        "orchestrate.md must reference static default of 2500 tokens"
    assert "< 7" in content, \
        "orchestrate.md must check sample_count < 7 for static default"


def test_orchestrate_uses_mean_when_cv_low():
    """T-033: orchestrate.md uses mean when sample_count >= 7 and cv < threshold."""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    assert "cv_threshold" in content, \
        "orchestrate.md must reference cv_threshold config"
    assert "mean" in content, \
        "orchestrate.md must specify mean as the cost estimate when CV is low"
    assert "cv" in content, \
        "orchestrate.md must compute CV (coefficient of variation)"


def test_orchestrate_uses_p85_when_cv_high():
    """T-033: orchestrate.md uses p85 when cv >= threshold."""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    assert "p85" in content or "85th" in content.lower(), \
        "orchestrate.md must use p85 (85th percentile) when cv >= cv_threshold"
    assert ">= cv_threshold" in content or "≥ cv_threshold" in content, \
        "orchestrate.md must specify p85 is used when cv >= cv_threshold"


def test_orchestrate_loads_prior_ewma_at_startup():
    """T-033: orchestrate.md loads prior EWMA from rate_calibration_claude.json at startup."""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    assert "ewma" in content.lower(), \
        "orchestrate.md must reference EWMA"
    assert "rate_calibration_claude.json" in content, \
        "orchestrate.md must reference rate_calibration_claude.json"
    assert "ewma_mean_tokens" in content, \
        "orchestrate.md must load ewma_mean_tokens from rate_calibration_claude.json"


def test_orchestrate_writes_ewma_to_rate_calibration():
    """T-033: orchestrate.md writes ewma_mean_tokens, ewma_cv, sample_count, ewma_alpha to rate_calibration_claude.json."""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    assert "ewma_mean_tokens" in content, \
        "orchestrate.md must write ewma_mean_tokens to rate_calibration_claude.json"
    assert "ewma_cv" in content, \
        "orchestrate.md must write ewma_cv to rate_calibration_claude.json"
    assert "sample_count" in content, \
        "orchestrate.md must write sample_count to rate_calibration_claude.json"
    assert "ewma_alpha" in content, \
        "orchestrate.md must write ewma_alpha to rate_calibration_claude.json"

