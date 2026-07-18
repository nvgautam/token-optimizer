"""State management and lifecycle tests for orchestrate skills."""
import pytest
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
CLAUDE_ORCHESTRATE = REPO / "commands" / "claude" / "orchestrate.md"
GEMINI_ORCHESTRATE = REPO / "commands" / "gemini" / "skills" / "orchestrate" / "SKILL.md"
AGY_ORCHESTRATE = REPO / ".agents" / "skills" / "orchestrate" / "SKILL.md"

# Only include files that exist — AGY SKILL.md is optional (created separately)
SKILL_FILES = [f for f in [CLAUDE_ORCHESTRATE, GEMINI_ORCHESTRATE, AGY_ORCHESTRATE] if f.exists()]


def test_orchestrate_pass2_cross_tier_routing():
    """T-114: Route Pass 2 reviewer to the opposite tier from the implementer (Claude only)."""
    for f in SKILL_FILES:
        if f == AGY_ORCHESTRATE:
            continue
        content = f.read_text(encoding="utf-8")
        assert "Pass 2" in content
        if "commands/claude" in str(f):
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
    required_sections = ["## Startup", "## Agent spawn", "## Review", "## Human gate", "## Merge"]
    for section in required_sections:
        assert section in content, f"Missing required section: {section}"


def test_orchestrate_extracted_files_exist():
    """T-139: Verify extracted helper files exist under commands/claude/orchestrator/."""
    orchestrator_dir = Path("commands/claude/orchestrator")
    expected_files = ["rate_pacing.md", "targeted_reads.md", "telemetry.md"]
    existing = [f for f in expected_files if (orchestrator_dir / f).exists()]
    assert len(existing) > 0, f"No extracted files found in {orchestrator_dir}"
    for file_name in existing:
        file_path = orchestrator_dir / file_name
        content = file_path.read_text(encoding="utf-8")
        assert len(content.strip()) > 0, f"Extracted file {file_path} is empty"


# T-069: Parallel scheduling via task_estimator + disjoint owns check

def test_claude_orchestrate_references_task_estimator():
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    assert "task_estimator" in content, "Claude orchestrate skill must reference task_estimator"


def test_gemini_orchestrate_references_task_estimator():
    content = GEMINI_ORCHESTRATE.read_text(encoding="utf-8")
    assert "task_estimator" in content, "Gemini orchestrate skill must reference task_estimator"


def test_claude_orchestrate_has_disjoint_owns_check():
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    assert "owns" in content.lower() and (
        "conflict" in content.lower()
        or "disjoint" in content.lower()
        or "overlap" in content.lower()
    ), "Claude orchestrate skill must have disjoint owns check"


def test_gemini_orchestrate_has_disjoint_owns_check():
    content = GEMINI_ORCHESTRATE.read_text(encoding="utf-8")
    assert "owns" in content.lower() and (
        "conflict" in content.lower()
        or "disjoint" in content.lower()
        or "overlap" in content.lower()
    ), "Gemini orchestrate skill must have disjoint owns check"


def test_claude_orchestrate_size_limit():
    lines = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 150, f"Claude orchestrate.md is {len(lines)} lines (limit 150)"


@pytest.mark.xfail(strict=True, reason="SKILL.md pre-existing size violation (245 lines) — tracked separately for refactor")
def test_gemini_orchestrate_size_limit():
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


def test_orchestrate_resume_derives_next_round_from_execution_plan():
    """T-278: Orchestrator must derive next_round from execution_plan.md, treating state.json as advisory."""
    CLAUDE_STARTUP = REPO / "commands" / "claude" / "orchestrator" / "startup.md"
    for f in [CLAUDE_ORCHESTRATE, CLAUDE_STARTUP, GEMINI_ORCHESTRATE]:
        if not f.exists():
            continue
        content = f.read_text(encoding="utf-8")
        assert "execution_plan.md" in content, f"{f.name} must reference execution_plan.md"
        assert "advisory" in content.lower(), f"{f.name} must state that state.json is advisory only"
        assert "deriv" in content.lower(), f"{f.name} must state next round is derived from execution_plan.md"
        assert "master round table" in content.lower(), f"{f.name} must reference Master Round Table"
        assert "pending" in content.lower(), f"{f.name} must scan for row whose tasks are all pending"
        assert "sole authority" in content.lower(), f"{f.name} must state state.json is not the sole authority for next_round"


def test_orchestrate_enforces_write_tool_for_current_round():
    """T-279: Enforce Write tool (not Bash) for current_round.json writes."""
    for f in SKILL_FILES:
        content = f.read_text(encoding="utf-8")
        assert "Write tool" in content and "current_round.json" in content
        assert "never Bash" in content or "never use Bash" in content.lower()


def test_orchestrate_startup_reconciliation():
    """T-280: Assert startup reconciliation step is present in both skill files."""
    for f in [CLAUDE_ORCHESTRATE, GEMINI_ORCHESTRATE]:
        content = f.read_text(encoding="utf-8")
        assert "current_round.json" in content
        assert "tasks.json" in content
        assert "complete" in content
        assert "unlink" in content
        assert "tasks_in_flight.json" in content
        assert "startup_reconciliation_cleaned" in content


# T-281: Round table [PENDING] tag format tests

def test_execution_plan_pending_rounds_tagged():
    """T-281: All pending rounds in execution_plan.md must have [PENDING] tag."""
    exec_plan = REPO / "execution_plan.md"
    content = exec_plan.read_text(encoding="utf-8")
    pending_lines = [line for line in content.split('\n') if '[PENDING]' in line]
    assert len(pending_lines) >= 4, f"Expected at least 4 rows with [PENDING] tag, found {len(pending_lines)}"
    assert any("Round C-pty [PENDING]" in line for line in pending_lines), \
        "Round C-pty must have [PENDING] tag"
    assert not any("Round A [PENDING]" in line for line in content.split('\n')), \
        "Merged Round A must not have [PENDING] tag"


def test_orchestrate_references_pending_tag_grep():
    """T-281: orchestrate.md must reference grep -m 1 '\\[PENDING\\]' for selecting next round."""
    content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
    assert "grep" in content.lower() and "PENDING" in content, \
        "orchestrate.md must reference grep with PENDING pattern"


def test_oracle_references_pending_tag_grep():
    """T-281: oracle.md must reference grep '\\[PENDING\\]' for identifying next pending round."""
    CLAUDE_ORACLE = REPO / "commands" / "claude" / "oracle.md"
    content = CLAUDE_ORACLE.read_text(encoding="utf-8")
    assert "[PENDING]" in content or "PENDING" in content, \
        "oracle.md must reference [PENDING] tag or PENDING pattern"
    assert "grep" in content.lower() or "execution_plan.md" in content, \
        "oracle.md must reference grep or execution_plan.md for finding next round"
