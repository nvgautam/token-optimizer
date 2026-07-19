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


def test_orchestrate_signals_and_round_json():
    """Assert all four signal strings and current_round.json write step are present."""
    for f in [CLAUDE_ORCHESTRATE, GEMINI_ORCHESTRATE]:
        content = f.read_text(encoding="utf-8")
        assert ".agentflow/current_round.json" in content, f"{f.name} must write .agentflow/current_round.json"
        assert "round_id" in content, f"{f.name} must include round_id in current_round.json write details"
        assert "task_ids" in content, f"{f.name} must include task_ids in current_round.json write details"
        assert "estimated_lines_per_task" in content, f"{f.name} must include estimated_lines_per_task in current_round.json write details"
        assert "file_counts_per_task" in content, f"{f.name} must include file_counts_per_task in current_round.json write details"
        assert "timestamp" in content, f"{f.name} must include timestamp in current_round.json write details"
        assert "AGENTFLOW_TASK_START:" in content, f"{f.name} must print AGENTFLOW_TASK_START:<task_id>"
        assert "AGENTFLOW_TASK_COMPLETE:" in content, f"{f.name} must print AGENTFLOW_TASK_COMPLETE:<task_id>"
        assert "AGENTFLOW_ROUND_COMPLETE" not in content, f"{f.name} must not print vestigial AGENTFLOW_ROUND_COMPLETE"


def test_orchestrate_skills_contain_verbosity_rules():
    """Assert that all orchestrate skill files define the ≤3 sentences verbosity limit."""
    for f in SKILL_FILES:
        content = f.read_text(encoding="utf-8")
        assert "≤3 sentences" in content or "<=3 sentences" in content or "less than or equal to 3 sentences" in content.lower(), \
            f"{f.name} must specify ≤3 sentences verbosity rule"
        assert "150 tokens" in content, f"{f.name} must specify 150 tokens verbosity limit"


def test_orchestrate_skills_contain_cleanup_tasks_merge():
    """Assert that all orchestrate skill files use the cleanup_tasks.py tool at merge time."""
    for f in SKILL_FILES:
        content = f.read_text(encoding="utf-8")
        assert "cleanup_tasks.py" in content, f"{f.name} must specify running cleanup_tasks.py in merge protocol"


def test_current_round_written_before_agent_spawn():
    """T-285: current_round.json must be written BEFORE Agent spawn, not after."""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    assert "BEFORE spawning" in content, \
        "orchestrate.md must explicitly state current_round.json is written BEFORE spawning"
    before_pos = content.lower().find("before spawning")
    spawn_pos = content.lower().find("spawn worker")
    assert before_pos != -1, "orchestrate.md must contain 'BEFORE spawning' text"
    assert spawn_pos != -1, "orchestrate.md must contain 'Spawn worker' text"
    assert before_pos < spawn_pos, \
        "current_round.json write instruction must appear before 'Spawn worker' in orchestrate.md"


def test_orchestrate_startup_reconciliation_mid_round_restart():
    """T-291: startup reconciliation must handle mid-round restarts with mixed complete/pending tasks."""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    assert "If ALL task_ids are complete" in content, \
        "orchestrate.md Step 4a must check if ALL task_ids are complete (stale case)"
    assert "startup_reconciliation_cleaned" in content, \
        "orchestrate.md Step 4a must log 'startup_reconciliation_cleaned' when all tasks are complete"
    assert "If SOME task_ids are complete and SOME are pending" in content, \
        "orchestrate.md Step 4a must handle mid-round restart case with mixed statuses"
    assert "filter to pending subset" in content, \
        "orchestrate.md Step 4a must filter to pending subset on mid-round restart"
    assert "startup_mid_round_resumed" in content, \
        "orchestrate.md Step 4a must log 'startup_mid_round_resumed' on mid-round restart"
    assert "If all are pending" in content, \
        "orchestrate.md Step 4a must handle all pending case"
    assert "at least one pending task" in content, \
        "orchestrate.md Step 4 must find first row with at least one pending task (not all pending)"


def test_context_bundle_delivered_via_temp_file():
    """T-234: orchestrate.md must instruct writing ctx bundle to temp file, not embedding in prompt."""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    assert ".agentflow/ctx-" in content, \
        "orchestrate.md must instruct writing context bundle to .agentflow/ctx-<session-id>.json"
    assert "ctx-" in content and ".json" in content, \
        "orchestrate.md must reference ctx file path pattern"
    # Worker reads and deletes the file
    assert "reads and deletes" in content or ("reads" in content and "deletes" in content), \
        "orchestrate.md must say worker reads and deletes the temp file"
    # Guard: missing file must error, not silently skip
    assert "missing file" in content.lower() or "file missing" in content.lower() or "gracefully" in content.lower(), \
        "orchestrate.md must document guard for missing ctx file"


def test_orchestrate_post_merge_conflict_resolution():
    """T-236: orchestrate.md Human gate must include post-merge conflict resolution step."""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    # Check for fetch origin/main
    assert "fetch origin/main" in content.lower() or "fetch" in content.lower() and "origin" in content.lower(), \
        "orchestrate.md must include fetch origin/main in post-merge conflict resolution"
    # Check for merge into PR branch
    assert "merge" in content.lower() and "pr" in content.lower(), \
        "orchestrate.md must include merge into PR branch in conflict resolution"
    # Check for auto-resolve additive conflicts (accept both sides)
    assert "auto-resolve" in content.lower() or "additive" in content.lower(), \
        "orchestrate.md must describe auto-resolving additive conflicts"
    assert "accept both sides" in content.lower(), \
        "orchestrate.md must specify accepting both sides for additive changes"
    # Check for escalation on same-line conflicts
    assert "escalate" in content.lower() and "conflict" in content.lower(), \
        "orchestrate.md must describe escalation on same-line conflicts"
    # Check for push and re-merge
    assert "push" in content.lower(), \
        "orchestrate.md must include pushing after conflict resolution"
    assert "re-merge" in content.lower() or "remerge" in content.lower(), \
        "orchestrate.md must include re-merging after push"
