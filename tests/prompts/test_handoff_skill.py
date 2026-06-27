# tests/prompts/test_handoff_skill.py
import re
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
HANDOFF_FILES = [
    REPO / "commands" / "handoff.md",
    REPO / ".agents" / "skills" / "handoff" / "SKILL.md"
]


def test_handoff_files_exist():
    for f in HANDOFF_FILES:
        assert f.exists(), f"{f} must exist"


def test_handoff_files_valid_utf8():
    for f in HANDOFF_FILES:
        f.read_text(encoding="utf-8")


def test_handoff_files_do_not_exceed_150_lines():
    for f in HANDOFF_FILES:
        lines = f.read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 150, f"{f.name} has {len(lines)} lines (max 150)"


def test_handoff_files_contain_handoff_complete_instruction():
    for f in HANDOFF_FILES:
        content = f.read_text(encoding="utf-8")
        assert "HANDOFF_COMPLETE" in content, \
            f"{f.name} must instruct printing HANDOFF_COMPLETE: <path>"


def test_handoff_files_use_agentflow_paths_not_claude_memory():
    for f in HANDOFF_FILES:
        content = f.read_text(encoding="utf-8")
        assert ".agentflow/" in content, f"{f.name} must use .agentflow/ paths"


def test_handoff_files_flush_state_to_architecture_md_for_oracle():
    for f in HANDOFF_FILES:
        content = f.read_text(encoding="utf-8").lower()
        assert "architecture.md" in content and "oracle" in content, \
            f"{f.name} must flush state to architecture.md for oracle sessions"


def test_handoff_files_flush_state_to_execution_plan_for_orchestrator():
    for f in HANDOFF_FILES:
        content = f.read_text(encoding="utf-8").lower()
        assert "execution_plan.md" in content and "orchestrat" in content, \
            f"{f.name} must flush state to execution_plan.md for orchestrator sessions"


def test_handoff_files_contain_compact_format_rule():
    for f in HANDOFF_FILES:
        content = f.read_text(encoding="utf-8").lower()
        assert ("table" in content or "bullet" in content) and "prose" in content, \
            f"{f.name} must specify compact format rule (tables/bullets, no prose)"


def test_handoff_files_document_handoff_recommended_signals():
    for f in HANDOFF_FILES:
        content = f.read_text(encoding="utf-8")
        assert "HANDOFF RECOMMENDED" in content, \
            f"{f.name} must document HANDOFF RECOMMENDED signal format"


def test_handoff_files_recommended_signal_includes_reason():
    for f in HANDOFF_FILES:
        content = f.read_text(encoding="utf-8")
        # Check that HANDOFF RECOMMENDED is shown with a reason parameter
        assert "HANDOFF RECOMMENDED:" in content, \
            f"{f.name} must include a reason (HANDOFF RECOMMENDED: <reason>)"


def test_handoff_complete_appears_as_last_step():
    for f in HANDOFF_FILES:
        content = f.read_text(encoding="utf-8")
        handoff_complete_pos = content.rfind("HANDOFF_COMPLETE")
        # HANDOFF_COMPLETE should appear in the latter half of the file (last step)
        assert handoff_complete_pos > len(content) // 2, \
            f"HANDOFF_COMPLETE in {f.name} should be in the last step (final output)"


def test_no_hardcoded_secrets_in_handoff():
    secret_pattern = re.compile(r'(password|api_key|secret)\s*=\s*["\'][^"\']{8,}', re.IGNORECASE)
    for f in HANDOFF_FILES:
        content = f.read_text(encoding="utf-8")
        assert not secret_pattern.search(content), f"{f.name} contains a possible hardcoded secret"
