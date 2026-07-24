"""Tests for disabling the rate-pacing first-agent-alone rule (T-356)."""
import pytest
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
CLAUDE_ORCHESTRATE = REPO / "commands" / "claude" / "orchestrate.md"
RATE_PACING_MD = REPO / "commands" / "claude" / "orchestrator" / "rate_pacing.md"


def test_orchestrate_does_not_require_first_agent_alone():
    """Verify that orchestrate.md no longer enforces 'spawn first agent alone' rule."""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    # The specific phrase about spawning first agent alone should be removed
    assert "Spawn first agent alone" not in content, \
        "orchestrate.md must not contain 'Spawn first agent alone' rule"


def test_rate_pacing_marked_as_disabled():
    """Verify that rate_pacing.md is marked as disabled."""
    content = RATE_PACING_MD.read_text(encoding="utf-8")
    # Should indicate it's disabled or deferred
    assert any(phrase in content.lower() for phrase in ["disabled", "deferred"]), \
        "rate_pacing.md must indicate it is disabled or deferred"


def test_orchestrate_retains_other_rate_pacing_logic():
    """Verify that other rate-pacing logic remains in orchestrate.md."""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    # Should still reference rate-pacing protocol
    assert "rate-pacing" in content.lower() or "rate pacing" in content.lower(), \
        "orchestrate.md must still reference rate-pacing (disabled)"
    # Should still check 3x pct_cost budget calculation
    assert ("3 × pct_cost" in content or "3x pct_cost" in content.lower() or "3 * pct_cost" in content), \
        "orchestrate.md must still check remaining budget against 3x pct_cost"


def test_rate_pacing_does_not_gate_parallel_spawning():
    """Verify that rate_pacing.md no longer gates parallel spawning."""
    content = RATE_PACING_MD.read_text(encoding="utf-8")
    # The first-agent-alone rule should be removed
    assert "First agent of every session: alone" not in content, \
        "rate_pacing.md must not contain 'First agent of every session: alone' rule"
