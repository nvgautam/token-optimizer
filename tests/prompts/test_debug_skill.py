# tests/prompts/test_debug_skill.py
# T-350: debug.md merged into ops.md; tests now target ops.md
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
OPS_SKILL = REPO / "commands" / "claude" / "ops.md"
DEBUG_SKILL = REPO / "commands" / "claude" / "debug.md"
CLAUDE_MD = REPO / "CLAUDE.md"


def test_debug_md_deleted():
    assert not DEBUG_SKILL.exists(), (
        "commands/claude/debug.md must be deleted after T-350 merge; "
        "content is now in ops.md"
    )


def test_ops_skill_exists():
    assert OPS_SKILL.exists(), "commands/claude/ops.md must exist"


def test_ops_skill_under_150_lines():
    lines = OPS_SKILL.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 150, f"ops.md has {len(lines)} lines (max 150)"


def test_ops_skill_covers_pty_stuck():
    content = OPS_SKILL.read_text(encoding="utf-8")
    assert "pty_audit.jsonl" in content or "PTY stuck" in content or "pty-stuck" in content.lower(), \
        "ops.md must cover the PTY-stuck symptom class"


def test_ops_skill_covers_drain_missed():
    content = OPS_SKILL.read_text(encoding="utf-8")
    assert "hook_drain_debug" in content or "drain-missed" in content.lower() or "drain_missed" in content, \
        "ops.md must cover the drain-missed symptom class"


def test_ops_skill_covers_split_brain():
    content = OPS_SKILL.read_text(encoding="utf-8")
    assert "split-brain" in content.lower() or "split_brain" in content or "tasks_in_flight" in content, \
        "ops.md must cover the split-brain symptom class"


def test_ops_skill_epistemic_discipline():
    content = OPS_SKILL.read_text(encoding="utf-8").lower()
    assert (
        "hypothesis" in content
        or "hypothes" in content
        or "uncertain" in content
        or "evidence gap" in content
        or "unverified" in content
        or "label" in content
    ), "ops.md must encode epistemic discipline around incomplete evidence"


def test_ops_skill_has_six_phases():
    content = OPS_SKILL.read_text(encoding="utf-8")
    phase_markers = [f"Phase {i}" for i in range(1, 7)]
    found = [m for m in phase_markers if m in content]
    assert len(found) == 6, (
        f"ops.md must contain exactly 6 numbered phases (Phase 1 through Phase 6); "
        f"found: {found}"
    )


def test_ops_skill_no_internal_only_framing():
    content = OPS_SKILL.read_text(encoding="utf-8")
    assert "Internal Only" not in content, (
        "ops.md must not carry 'Internal Only' framing after T-350 merge"
    )


def test_ops_skill_no_state_json_session_lookup():
    content = OPS_SKILL.read_text(encoding="utf-8")
    assert "active_session_id" not in content, (
        "ops.md must not use state.json['active_session_id'] for SID lookup "
        "(T-250 fix: read session_id from current_round.json instead)"
    )


def test_ops_skill_uses_current_round_for_sid():
    content = OPS_SKILL.read_text(encoding="utf-8")
    assert "current_round.json" in content, (
        "ops.md must read session_id from current_round.json (T-250 fix)"
    )


def test_ops_skill_references_signal_files():
    content = OPS_SKILL.read_text(encoding="utf-8")
    assert "pty_audit.jsonl" in content, "ops.md must reference pty_audit.jsonl"
    assert "hook_drain_debug.jsonl" in content, "ops.md must reference hook_drain_debug.jsonl"
    assert "current_round.json" in content, "ops.md must reference current_round.json"


def test_claude_md_troubleshooting_reference():
    content = CLAUDE_MD.read_text(encoding="utf-8")
    assert "commands/claude/ops.md" in content, (
        "CLAUDE.md must reference commands/claude/ops.md for troubleshooting auto-load"
    )
