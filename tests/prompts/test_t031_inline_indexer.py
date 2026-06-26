"""Content assertion tests for T-031: Inline .idx generation in orchestrate skill."""
import pathlib

REPO = pathlib.Path(__file__).parent.parent.parent
ORCHESTRATE = REPO / "commands" / "orchestrate.md"
WORKER_SYSTEM = REPO / "commands" / "worker" / "system.md"


def test_orchestrate_idx_python_ast():
    """orchestrate.md pre-spawn section includes .idx generation for Python files using ast."""
    content = ORCHESTRATE.read_text()
    assert "ast" in content, "Expected 'ast' in orchestrate.md for Python .idx generation"
    assert ".idx" in content, "Expected '.idx' in orchestrate.md"


def test_orchestrate_idx_markdown_grep_h2_h3():
    """orchestrate.md pre-spawn section includes .idx generation for Markdown files (grep H2/H3)."""
    content = ORCHESTRATE.read_text()
    assert "H2/H3" in content, "Expected 'H2/H3' in orchestrate.md for Markdown .idx generation"


def test_orchestrate_idx_cache_path():
    """orchestrate.md specifies cache path ~/.agentflow/cache/<hash>/index/."""
    content = ORCHESTRATE.read_text()
    assert "~/.agentflow/cache/" in content, (
        "Expected '~/.agentflow/cache/' in orchestrate.md"
    )


def test_worker_system_targeted_reads():
    """worker/system.md includes targeted reads instruction: grep .idx then Read(offset, limit)."""
    content = WORKER_SYSTEM.read_text()
    assert ".idx" in content, "Expected '.idx' in worker/system.md"
    assert "grep" in content, "Expected 'grep' in worker/system.md for .idx lookup"
    assert "offset" in content, "Expected 'offset' in worker/system.md for Read() call"
    assert "limit" in content, "Expected 'limit' in worker/system.md for Read() call"


def test_worker_system_fallback_full_read():
    """worker/system.md includes fallback to full file read when .idx absent or symbol not found."""
    content = WORKER_SYSTEM.read_text()
    lower = content.lower()
    assert "fallback" in lower or "absent" in lower or "full file" in lower, (
        "Expected fallback instruction in worker/system.md"
    )
