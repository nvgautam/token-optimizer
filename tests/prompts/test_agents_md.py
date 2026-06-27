# tests/prompts/test_agents_md.py
"""Tests for .agents/AGENTS.md — the Antigravity developer rules file."""
import re
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
AGENTS_MD = REPO / ".agents" / "AGENTS.md"


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
