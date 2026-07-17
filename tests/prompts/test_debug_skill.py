# tests/prompts/test_debug_skill.py
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
DEBUG_SKILL = REPO / "commands" / "claude" / "debug.md"


def test_debug_skill_under_150_lines():
    lines = DEBUG_SKILL.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 150, f"debug.md has {len(lines)} lines (max 150)"


def test_debug_skill_covers_pty_stuck():
    content = DEBUG_SKILL.read_text(encoding="utf-8")
    assert "pty_audit.jsonl" in content or "PTY stuck" in content or "pty-stuck" in content.lower(), \
        "debug.md must cover the PTY-stuck symptom class"


def test_debug_skill_covers_drain_missed():
    content = DEBUG_SKILL.read_text(encoding="utf-8")
    assert "hook_drain_debug" in content or "drain-missed" in content.lower() or "drain_missed" in content, \
        "debug.md must cover the drain-missed symptom class"


def test_debug_skill_covers_split_brain():
    content = DEBUG_SKILL.read_text(encoding="utf-8")
    assert "split-brain" in content.lower() or "split_brain" in content or "tasks_in_flight" in content, \
        "debug.md must cover the split-brain symptom class"


def test_debug_skill_epistemic_discipline():
    content = DEBUG_SKILL.read_text(encoding="utf-8").lower()
    assert (
        "hypothesis" in content
        or "hypothes" in content
        or "uncertain" in content
        or "evidence gap" in content
        or "unverified" in content
        or "label" in content
    ), "debug.md must encode epistemic discipline around incomplete evidence"


def test_debug_skill_has_five_phases():
    content = DEBUG_SKILL.read_text(encoding="utf-8")
    phase_markers = [f"Phase {i}" for i in range(1, 6)]
    found = [m for m in phase_markers if m in content]
    assert len(found) == 5, (
        f"debug.md must contain exactly 5 numbered phases (Phase 1 through Phase 5); "
        f"found: {found}"
    )


def test_debug_skill_no_state_json_session_lookup():
    content = DEBUG_SKILL.read_text(encoding="utf-8")
    assert "active_session_id" not in content, (
        "debug.md must not use state.json['active_session_id'] for SID lookup "
        "(T-250 fix: read session_id from current_round.json instead)"
    )


def test_debug_skill_uses_current_round_for_sid():
    content = DEBUG_SKILL.read_text(encoding="utf-8")
    assert "current_round.json" in content, (
        "debug.md must read session_id from current_round.json (T-250 fix)"
    )
