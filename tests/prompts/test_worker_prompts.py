# tests/prompts/test_worker_prompts.py
import re
from pathlib import Path

WORKER_DIR = Path("commands/claude/worker")

def test_all_worker_prompt_files_valid_utf8():
    for f in ["system.md", "context_bundle.md", "testing_guide.md"]:
        (WORKER_DIR / f).read_text(encoding="utf-8")

def test_no_worker_prompt_file_exceeds_150_lines():
    for f in ["system.md", "context_bundle.md", "testing_guide.md"]:
        lines = (WORKER_DIR / f).read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 150, f"{f} has {len(lines)} lines (max 150)"

def test_system_md_contains_no_reread_rule():
    content = (WORKER_DIR / "system.md").read_text(encoding="utf-8")
    assert "Do not use the Read tool" in content or "do not re-read" in content.lower(), \
        "system.md missing no-re-read rule"

def test_system_md_no_reread_rule_appears_before_task_section():
    content = (WORKER_DIR / "system.md").read_text(encoding="utf-8")
    no_reread_pos = content.lower().find("do not use the read tool") if "do not use the Read tool" not in content else content.find("Do not use the Read tool")
    # The rule should appear in the first half of the file (before task-specific sections)
    assert no_reread_pos < len(content) // 2, "no-re-read rule should appear early in system.md"

def test_system_md_contains_verbosity_instruction():
    content = (WORKER_DIR / "system.md").read_text(encoding="utf-8").lower()
    assert "concise" in content or "verbose" in content, "system.md missing verbosity instruction"

def test_system_md_contains_escalate_instruction():
    content = (WORKER_DIR / "system.md").read_text(encoding="utf-8")
    assert "ESCALATE" in content, "system.md missing ESCALATE instruction"

def test_system_md_contains_tokens_report_instruction():
    content = (WORKER_DIR / "system.md").read_text(encoding="utf-8")
    assert "TOKENS:" in content, "system.md missing TOKENS: report instruction"

def test_testing_guide_contains_tdd_instruction():
    content = (WORKER_DIR / "testing_guide.md").read_text(encoding="utf-8").lower()
    assert "red" in content and "green" in content, "testing_guide.md missing red→green TDD instruction"

def test_testing_guide_contains_behaviour_not_implementation():
    content = (WORKER_DIR / "testing_guide.md").read_text(encoding="utf-8").lower()
    assert "behaviour" in content or "behavior" in content, \
        "testing_guide.md missing behaviour-not-implementation instruction"

def test_testing_guide_contains_io_mock_section():
    content = (WORKER_DIR / "testing_guide.md").read_text(encoding="utf-8").lower()
    assert "mock" in content, "testing_guide.md missing IO mock section"

def test_no_hardcoded_secrets_in_worker_prompts():
    secret_pattern = re.compile(r'(password|api_key|secret)\s*=\s*["\'][^"\']{8,}', re.IGNORECASE)
    for f in ["system.md", "context_bundle.md", "testing_guide.md"]:
        content = (WORKER_DIR / f).read_text(encoding="utf-8")
        assert not secret_pattern.search(content), f"Possible hardcoded secret in {f}"

def test_orchestrate_md_merge_section_contains_tasks_json_sync():
    orchestrate_path = Path("commands/claude/orchestrate.md")
    content = orchestrate_path.read_text(encoding="utf-8")
    merge_section = content[content.find("## Merge"):] if "## Merge" in content else ""
    assert "tasks.json" in merge_section or "cleanup_tasks.py" in merge_section, \
        "Merge section must mention tasks.json or cleanup_tasks.py for atomic sync"

def test_worker_system_md_workflow_contains_tasks_json_write():
    content = (WORKER_DIR / "system.md").read_text(encoding="utf-8")
    workflow_section = content[content.find("## Workflow"):] if "## Workflow" in content else ""
    assert "tasks.json" in workflow_section and ("MERGED" in workflow_section or "merged" in workflow_section), \
        "Workflow must instruct workers to write tasks.json when marking MERGED"
