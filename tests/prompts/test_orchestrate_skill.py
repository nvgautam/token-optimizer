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
        assert "AGENTFLOW_ROUND_COMPLETE" in content, f"{f.name} must print AGENTFLOW_ROUND_COMPLETE"


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






def test_orchestrate_pass2_cross_tier_routing():
    """T-114: Route Pass 2 reviewer to the opposite tier from the implementer (Claude only)."""
    for f in SKILL_FILES:
        if f == AGY_ORCHESTRATE:
            continue
        content = f.read_text(encoding="utf-8")
        assert "Pass 2" in content
        if "commands/claude" in str(f):
            # Assert cross-tier reviewer routing rule is present
            assert "opposite tier" in content.lower() or "cross-tier" in content.lower()
            assert "haiku-implemented" in content.lower()
            assert "sonnet-implemented" in content.lower()


def test_gemini_orchestrate_no_8b():
    """T-214: Assert gemini-1.5-flash-8b does not appear in Gemini orchestrate skill content."""
    content = GEMINI_ORCHESTRATE.read_text(encoding="utf-8")
    assert "gemini-1.5-flash-8b" not in content, "gemini-1.5-flash-8b must not appear in Gemini orchestrate skill"
    assert "flash low" not in content.lower(), "flash low must not appear in Gemini orchestrate skill"



def test_orchestrate_skills_contain_pty_signal():
    """Verify that both Claude and Gemini skills call pty_signal.py for task status updates."""
    for f in [CLAUDE_ORCHESTRATE, GEMINI_ORCHESTRATE]:
        content = f.read_text(encoding="utf-8")
        assert "pty_signal.py" in content, f"{f.name} must call pty_signal.py"


def test_orchestrate_file_size():
    """T-139: orchestrate.md must be <= 150 lines."""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    lines = len(content.rstrip('\n').split('\n'))
    assert lines <= 150, f"commands/claude/orchestrate.md is {lines} lines (limit: 150)"


def test_orchestrate_required_sections_t139():
    """T-139: orchestrate.md must contain core sections after split."""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")

    required_sections = [
        "## Startup",
        "## Agent spawn",
        "## Review",
        "## Human gate",
        "## Merge",
    ]

    for section in required_sections:
        assert section in content, f"Missing required section: {section}"


def test_orchestrate_extracted_files_exist():
    """T-139: Verify extracted helper files exist under commands/claude/orchestrator/."""
    orchestrator_dir = Path("commands/claude/orchestrator")

    # These files should be extracted
    expected_files = [
        "rate_pacing.md",
        "targeted_reads.md",
        "telemetry.md",
    ]

    # At least some extracted files must exist
    existing = [f for f in expected_files if (orchestrator_dir / f).exists()]
    assert len(existing) > 0, f"No extracted files found in {orchestrator_dir}"

    # Each existing extracted file must be non-empty
    for file_name in existing:
        file_path = orchestrator_dir / file_name
        content = file_path.read_text(encoding="utf-8")
        assert len(content.strip()) > 0, f"Extracted file {file_path} is empty"


# T-069: Parallel scheduling via task_estimator + disjoint owns check

def test_claude_orchestrate_references_task_estimator():
    """orchestrate.md must reference agentflow.shadow.task_estimator"""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    assert "task_estimator" in content, "Claude orchestrate skill must reference task_estimator"


def test_gemini_orchestrate_references_task_estimator():
    """SKILL.md must reference task_estimator"""
    content = GEMINI_ORCHESTRATE.read_text(encoding="utf-8")
    assert "task_estimator" in content, "Gemini orchestrate skill must reference task_estimator"


def test_claude_orchestrate_has_disjoint_owns_check():
    """orchestrate.md must contain disjoint owns check instruction"""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    assert "owns" in content.lower() and (
        "conflict" in content.lower()
        or "disjoint" in content.lower()
        or "overlap" in content.lower()
    ), "Claude orchestrate skill must have disjoint owns check"


def test_gemini_orchestrate_has_disjoint_owns_check():
    """SKILL.md must contain disjoint owns check instruction"""
    content = GEMINI_ORCHESTRATE.read_text(encoding="utf-8")
    assert "owns" in content.lower() and (
        "conflict" in content.lower()
        or "disjoint" in content.lower()
        or "overlap" in content.lower()
    ), "Gemini orchestrate skill must have disjoint owns check"


def test_claude_orchestrate_size_limit():
    """orchestrate.md must not exceed 150 lines (CLAUDE.md prompts constraint)"""
    lines = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 150, f"Claude orchestrate.md is {len(lines)} lines (limit 150)"


@pytest.mark.xfail(strict=True, reason="SKILL.md pre-existing size violation (245 lines) — tracked separately for refactor")
def test_gemini_orchestrate_size_limit():
    """SKILL.md must not exceed 150 lines (CLAUDE.md prompts constraint)"""
    lines = GEMINI_ORCHESTRATE.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 150, f"Gemini SKILL.md is {len(lines)} lines (limit 150)"


# T-230: Worktree lifecycle — orchestrator pre-creates, worker enters

def test_orchestrate_pre_creates_worktree():
    """T-230: orchestrate.md must instruct orchestrator to pre-create worktree before spawning."""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    assert "git worktree add" in content, \
        "orchestrate.md must instruct orchestrator to run `git worktree add` before spawning"
    assert ".claude/worktrees/" in content, \
        "orchestrate.md must specify .claude/worktrees/ as the worktree location"


def test_orchestrate_bans_git_checkout_in_root():
    """T-230: orchestrate.md must explicitly ban `git checkout` in the project root."""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    assert "Never" in content and "git checkout" in content, \
        "orchestrate.md must explicitly ban `git checkout` in the project root"
    assert "git show" in content or "gh pr diff" in content, \
        "orchestrate.md must provide branch-safe inspection alternatives"


def test_orchestrate_worker_enters_existing_worktree():
    """T-230: orchestrate.md must instruct worker to call EnterWorktree with pre-created path."""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    assert "EnterWorktree" in content, \
        "orchestrate.md must reference EnterWorktree for workers to enter pre-created worktrees"
