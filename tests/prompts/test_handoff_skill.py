# tests/prompts/test_handoff_skill.py
import re
from pathlib import Path

HANDOFF_FILE = Path(__file__).parent.parent.parent / "commands" / "handoff.md"


def test_handoff_md_exists():
    assert HANDOFF_FILE.exists(), "commands/handoff.md must exist"


def test_handoff_md_valid_utf8():
    HANDOFF_FILE.read_text(encoding="utf-8")


def test_handoff_md_does_not_exceed_150_lines():
    lines = HANDOFF_FILE.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 150, f"commands/handoff.md has {len(lines)} lines (max 150)"


def test_handoff_md_contains_handoff_complete_instruction():
    content = HANDOFF_FILE.read_text(encoding="utf-8")
    assert "HANDOFF_COMPLETE" in content, \
        "commands/handoff.md must instruct printing HANDOFF_COMPLETE: <path>"


def test_handoff_md_uses_agentflow_paths_not_claude_memory():
    content = HANDOFF_FILE.read_text(encoding="utf-8")
    assert ".agentflow/" in content, "commands/handoff.md must use .agentflow/ paths"
    # The old path .claude/memory/ should not be the primary storage path
    # (it may appear in migration notes but .agentflow/ must be the canonical path)


def test_handoff_md_flushes_state_to_architecture_md_for_oracle():
    content = HANDOFF_FILE.read_text(encoding="utf-8").lower()
    assert "architecture.md" in content and "oracle" in content, \
        "commands/handoff.md must flush state to architecture.md for oracle sessions"


def test_handoff_md_flushes_state_to_execution_plan_for_orchestrator():
    content = HANDOFF_FILE.read_text(encoding="utf-8").lower()
    assert "execution_plan.md" in content and "orchestrat" in content, \
        "commands/handoff.md must flush state to execution_plan.md for orchestrator sessions"


def test_handoff_md_contains_compact_format_rule():
    content = HANDOFF_FILE.read_text(encoding="utf-8").lower()
    assert ("table" in content or "bullet" in content) and "prose" in content, \
        "commands/handoff.md must specify compact format rule (tables/bullets, no prose)"


def test_handoff_md_documents_handoff_recommended_signals():
    content = HANDOFF_FILE.read_text(encoding="utf-8")
    assert "HANDOFF RECOMMENDED" in content, \
        "commands/handoff.md must document HANDOFF RECOMMENDED signal format"


def test_handoff_md_recommended_signal_includes_reason():
    content = HANDOFF_FILE.read_text(encoding="utf-8")
    # Check that HANDOFF RECOMMENDED is shown with a reason parameter
    assert "HANDOFF RECOMMENDED:" in content, \
        "HANDOFF RECOMMENDED must include a reason (HANDOFF RECOMMENDED: <reason>)"


def test_handoff_complete_appears_as_last_step():
    content = HANDOFF_FILE.read_text(encoding="utf-8")
    handoff_complete_pos = content.rfind("HANDOFF_COMPLETE")
    # HANDOFF_COMPLETE should appear in the latter half of the file (last step)
    assert handoff_complete_pos > len(content) // 2, \
        "HANDOFF_COMPLETE should be in the last step (final output)"


def test_no_hardcoded_secrets_in_handoff():
    secret_pattern = re.compile(r'(password|api_key|secret)\s*=\s*["\'][^"\']{8,}', re.IGNORECASE)
    content = HANDOFF_FILE.read_text(encoding="utf-8")
    assert not secret_pattern.search(content), "commands/handoff.md contains a possible hardcoded secret"
