# tests/prompts/test_reviewer_prompts.py
import re
from pathlib import Path

REVIEWER_DIR = Path("commands/claude/reviewer")
ORCHESTRATOR_DIR = Path("commands/claude/orchestrator")

def test_all_reviewer_prompt_files_valid_utf8():
    for f in [REVIEWER_DIR / "code_review.md", REVIEWER_DIR / "security_review.md",
              REVIEWER_DIR / "test_review.md", ORCHESTRATOR_DIR / "planning.md"]:
        f.read_text(encoding="utf-8")

def test_no_reviewer_prompt_file_exceeds_150_lines():
    for f in [REVIEWER_DIR / "code_review.md", REVIEWER_DIR / "security_review.md",
              REVIEWER_DIR / "test_review.md", ORCHESTRATOR_DIR / "planning.md"]:
        lines = f.read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 150, f"{f.name} has {len(lines)} lines (max 150)"

def test_security_review_md_references_owasp_top_10():
    content = (REVIEWER_DIR / "security_review.md").read_text(encoding="utf-8")
    assert "OWASP" in content, "security_review.md must reference OWASP Top 10"

def test_security_review_md_contains_untrusted_diff_instruction():
    content = (REVIEWER_DIR / "security_review.md").read_text(encoding="utf-8").lower()
    assert "untrusted" in content, "security_review.md must contain untrusted-diff instruction"
    assert "diff" in content, "security_review.md must reference PR diff as untrusted"

def test_security_review_md_never_echoes_secrets():
    content = (REVIEWER_DIR / "security_review.md").read_text(encoding="utf-8").lower()
    assert "never echo" in content or "do not echo" in content or "never repeat" in content, \
        "security_review.md must instruct reviewer never to echo secret values"

def test_code_review_md_contains_contract_adherence():
    content = (REVIEWER_DIR / "code_review.md").read_text(encoding="utf-8").lower()
    assert "contract" in content or "stub" in content, \
        "code_review.md missing contract adherence check"

def test_code_review_md_contains_architecture_conformance():
    content = (REVIEWER_DIR / "code_review.md").read_text(encoding="utf-8").lower()
    assert "architecture" in content and ("drift" in content or "conformance" in content), \
        "code_review.md missing architecture conformance / drift check"

def test_test_review_md_contains_scenario_coverage():
    content = (REVIEWER_DIR / "test_review.md").read_text(encoding="utf-8").lower()
    assert "scenario" in content or "coverage" in content, \
        "test_review.md missing scenario coverage check"

def test_test_review_md_contains_mock_appropriateness():
    content = (REVIEWER_DIR / "test_review.md").read_text(encoding="utf-8").lower()
    assert "mock" in content, "test_review.md missing mock appropriateness check"

def test_planning_md_contains_milestone_decomposition_format():
    content = (ORCHESTRATOR_DIR / "planning.md").read_text(encoding="utf-8")
    assert "task_id" in content, "planning.md missing task definition schema (task_id field)"
    assert "owns" in content, "planning.md missing task definition schema (owns field)"

def test_planning_md_contains_round_definition_format():
    content = (ORCHESTRATOR_DIR / "planning.md").read_text(encoding="utf-8").lower()
    assert "round" in content, "planning.md missing round definition format"

def test_no_hardcoded_secrets_in_reviewer_prompts():
    secret_pattern = re.compile(r'(password|api_key|secret)\s*=\s*["\'][^"\']{8,}', re.IGNORECASE)
    for f in [REVIEWER_DIR / "code_review.md", REVIEWER_DIR / "security_review.md",
              REVIEWER_DIR / "test_review.md", ORCHESTRATOR_DIR / "planning.md"]:
        content = f.read_text(encoding="utf-8")
        assert not secret_pattern.search(content), f"Possible hardcoded secret in {f.name}"

def test_review_md_happy_path_only_is_blocker():
    content = (REVIEWER_DIR / "test_review.md").read_text(encoding="utf-8")
    # Should escalate happy-path-only scenarios to BLOCKER
    assert "BLOCKER" in content
    # Ideally find the line about "happy path" and ensure BLOCKER is near it
    lines = content.splitlines()
    found = any("happy path" in line.lower() and "blocker" in line.lower() for line in lines)
    assert found, "test_review.md must escalate happy-path-only coverage to BLOCKER"

def test_review_md_test_reimplements_feature_is_blocker():
    content = (REVIEWER_DIR / "test_review.md").read_text(encoding="utf-8")
    lines = content.splitlines()
    # Find section 5 and ensure BLOCKER or CRITICAL output includes BLOCKER label
    found = any("re-implement" in line.lower() and ("blocker" in line.lower() or "critical" in line.lower()) for line in lines)
    assert found, "test_review.md must flag re-implementation of feature as BLOCKER/CRITICAL"
    # Also assert that the output format actually contains BLOCKER
    assert "BLOCKER" in content, "test_review.md must define BLOCKER in its output format"

def test_orchestrate_md_review_gate_required():
    content = Path("commands/claude/orchestrate.md").read_text(encoding="utf-8")
    assert "/review" in content and "before opening" in content.lower(), "orchestrate.md must require /review before opening a PR"

def test_orchestrate_md_no_blockers_required():
    content = Path("commands/claude/orchestrate.md").read_text(encoding="utf-8")
    assert "zero blockers" in content.lower() or "no blockers" in content.lower(), "orchestrate.md must require zero BLOCKERs from the reviewer"

