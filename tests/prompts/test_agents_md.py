# tests/prompts/test_agents_md.py
"""Tests for .agents/AGENTS.md — the Antigravity developer rules file."""
import re
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
AGENTS_MD = REPO / "commands" / "gemini" / "AGENTS.md"


def test_agents_md_exists():
    assert AGENTS_MD.exists(), ".agents/AGENTS.md must exist"


def test_agents_md_valid_utf8():
    AGENTS_MD.read_text(encoding="utf-8")


def test_agents_md_contains_development_commands():
    content = AGENTS_MD.read_text(encoding="utf-8")
    assert "pytest tests/" in content, "AGENTS.md should specify the test command"
    assert "ruff check" in content or "ruff check ." in content, "AGENTS.md should specify the lint command"


def test_agents_md_contains_key_constraints():
    content = AGENTS_MD.read_text(encoding="utf-8")
    assert "no secrets" in content.lower(), "AGENTS.md should mandate no secrets"
    assert "file size" in content.lower() or "ceiling" in content.lower() or "lines" in content.lower(), \
        "AGENTS.md should specify the file size limit constraints"


def test_no_hardcoded_secrets_in_agents_md():
    secret_pattern = re.compile(r'(password|api_key|secret)\s*=\s*["\'][^"\']{8,}', re.IGNORECASE)
    content = AGENTS_MD.read_text(encoding="utf-8")
    assert not secret_pattern.search(content), "AGENTS.md contains a possible hardcoded secret"


def test_no_dead_headless_layer_paths_in_agents_md():
    # Clean up temporary/scratch files first if present
    for temp_file in [REPO / "tests" / "test_temp_update.py", REPO / "update_agents.py"]:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass

    content = AGENTS_MD.read_text(encoding="utf-8")
    dead_paths = [
        "agentflow/oracle/prompts/",
        "agentflow/worker/prompts/",
        "agentflow/reviewer/prompts/",
        "agentflow/orchestrator/prompts/",
    ]
    for path in dead_paths:
        assert path not in content, f"AGENTS.md must not reference dead path: {path}"

    agents_md_dot = REPO / ".agents" / "AGENTS.md"
    if agents_md_dot.exists():
        content_dot = agents_md_dot.read_text(encoding="utf-8")
        for path in dead_paths:
            assert path not in content_dot, f".agents/AGENTS.md must not reference dead path: {path}"
