import os
import pytest
from pathlib import Path
from unittest.mock import patch

from agentflow.indexer.brownfield_scanner import scan, ScanResult
from agentflow.indexer.index_manager import lookup


@pytest.fixture
def mock_home(tmp_path, monkeypatch):
    """Redirect home directory to a temp path for safe cache testing."""
    home_dir = tmp_path / "home"
    home_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home_dir))
    agentflow_dir = home_dir / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)
    return home_dir


@pytest.fixture
def dummy_project(tmp_path):
    """Create a dummy project structure with files of various types and sizes."""
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "pyproject.toml").touch()  # Project marker
    
    # 1. Eligible Python file (>= 50 lines)
    py_large = project_dir / "large.py"
    py_large.write_text("class TargetClass:\n" + "\n" * 50 + "    def test_method(self):\n        pass\n", encoding="utf-8")
    
    # 2. Ineligible Python file (< 50 lines)
    py_small = project_dir / "small.py"
    py_small.write_text("def small_func():\n    pass\n", encoding="utf-8")
    
    # 3. Eligible Markdown file (>= 50 lines)
    md_large = project_dir / "large.md"
    md_large.write_text("## Main Header\n" + "\n" * 50 + "### Sub Header\n", encoding="utf-8")
    
    # 4. Non-Python/Markdown file (>= 50 lines, but skipped)
    txt_large = project_dir / "large.txt"
    txt_large.write_text("line\n" * 60, encoding="utf-8")
    
    return project_dir


def test_brownfield_scan_returns_count_of_files_indexed(mock_home, dummy_project):
    """scan returns count of files indexed."""
    result = scan(dummy_project)
    
    # Expected eligible files: large.py and large.md (2 files)
    assert result.indexed == 2
    assert int(result) == 2
    assert result == 2


def test_brownfield_scan_skips_files_below_size_threshold(mock_home, dummy_project):
    """scan skips files below size threshold (< 50 lines) or non-py/md files."""
    result = scan(dummy_project)
    
    # Skipped: small.py, large.txt, and pyproject.toml (3 files)
    assert result.skipped == 3


def test_brownfield_scan_is_idempotent(mock_home, dummy_project):
    """scan is idempotent — running it twice does not re-write/corrupt cache and returns same count."""
    result1 = scan(dummy_project)
    assert result1.indexed == 2
    
    result2 = scan(dummy_project)
    assert result2.indexed == 2
    assert result2 == 2


def test_scan_project_fixture_tree_and_lookup_integration(mock_home, dummy_project):
    """scan project tree, then lookup symbol — returns correct entry."""
    scan(dummy_project)
    
    # Look up Class in large.py
    py_file = dummy_project / "large.py"
    entry = lookup(py_file, "TargetClass")
    assert entry is not None
    assert entry.name == "TargetClass"
    assert entry.kind == "class"
    
    # Look up Header in large.md
    md_file = dummy_project / "large.md"
    entry_md = lookup(md_file, "## Main Header")
    assert entry_md is not None
    assert entry_md.name == "## Main Header"
    assert entry_md.kind == "section"


def test_scan_result_methods():
    """Test ScanResult comparison, indexing, and conversion methods."""
    res = ScanResult(indexed=5, skipped=3, duration_ms=10)
    
    # int() and index check
    assert int(res) == 5
    assert hex(res) == "0x5"
    
    # Comparison check
    assert res == 5
    assert res != 3
    assert res == ScanResult(indexed=5, skipped=3, duration_ms=20)
    assert res != ScanResult(indexed=5, skipped=4, duration_ms=10)
    assert res != "not an integer"


def test_scan_file_read_error(mock_home, dummy_project):
    """scan handles OSError on reading files gracefully."""
    # Mock read_text to raise OSError
    with patch("pathlib.Path.read_text", side_effect=OSError("Read error")):
        result = scan(dummy_project)
        # All files will fail to read, so they should be counted as skipped
        # Skip count: 3 (small.py, large.txt, pyproject.toml) + 2 (large.py, large.md) = 5
        assert result.skipped == 5
        assert result.indexed == 0


def test_scan_get_cache_path_error(mock_home, dummy_project):
    """scan skips files where get_cache_path fails."""
    with patch("agentflow.indexer.index_manager.get_cache_path", side_effect=ValueError("Validation error")):
        result = scan(dummy_project)
        assert result.indexed == 0
        assert result.skipped == 5


def test_scan_update_error(mock_home, dummy_project):
    """scan skips files where index update fails."""
    # We mock update to raise ValueError
    with patch("agentflow.indexer.index_manager.update", side_effect=ValueError("Update error")):
        result = scan(dummy_project)
        assert result.indexed == 0
        assert result.skipped == 5
