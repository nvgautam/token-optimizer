import os
import hashlib
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

from agentflow.indexer import IndexEntry
from agentflow.indexer.index_manager import (
    update, lookup, get_index, get_cache_path,
    find_project_root, parse_contents, update_index
)


@pytest.fixture
def mock_home(tmp_path, monkeypatch):
    """Redirect home directory to a temp path for safe cache testing."""
    home_dir = tmp_path / "home"
    home_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home_dir))
    # Create the mocked ~/.agentflow directory to satisfy resolution/existence checks
    agentflow_dir = home_dir / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)
    return home_dir


@pytest.fixture
def dummy_project(tmp_path):
    """Create a dummy project structure with a pyproject.toml marker."""
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "pyproject.toml").touch()
    return project_dir


def test_update_writes_idx_file_at_correct_cache_path(mock_home, dummy_project):
    """update writes .idx file at correct cache path under ~/.agentflow."""
    file_path = dummy_project / "agentflow" / "tools" / "git.py"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 50 lines of python code to satisfy parser line threshold
    contents = "class GitTool:\n" + "\n" * 50 + "    def run(self):\n        pass\n"
    file_path.write_text(contents, encoding="utf-8")
    
    update(file_path, contents)
    
    # Verify the cache file is created at the correct location
    project_hash = hashlib.sha256(str(dummy_project.resolve()).encode("utf-8")).hexdigest()
    expected_cache_path = mock_home / ".agentflow" / "cache" / project_hash / "index" / "agentflow" / "tools" / "git.py.idx"
    assert expected_cache_path.exists()
    
    # Check the plaintext format of the .idx file: name:start-end
    idx_content = expected_cache_path.read_text(encoding="utf-8")
    lines = idx_content.splitlines()
    assert len(lines) == 2
    assert "GitTool:1-" in lines[0]  # class start
    assert "GitTool.run:52-" in lines[1]  # method start


def test_lookup_returns_correct_index_entry_for_known_symbol(mock_home, dummy_project):
    """lookup returns correct IndexEntry for known symbol."""
    file_path = dummy_project / "agentflow" / "tools" / "git.py"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    contents = "class GitTool:\n" + "\n" * 50 + "    def run(self):\n        pass\n"
    file_path.write_text(contents, encoding="utf-8")
    
    update(file_path, contents)
    entry = lookup(file_path, "GitTool")
    assert entry is not None
    assert entry.name == "GitTool"
    assert entry.kind == "class"
    
    entry_method = lookup(file_path, "GitTool.run")
    assert entry_method is not None
    assert entry_method.name == "GitTool.run"
    assert entry_method.kind == "method"


def test_lookup_returns_none_for_unknown_symbol(mock_home, dummy_project):
    """lookup returns None for unknown symbol."""
    file_path = dummy_project / "agentflow" / "tools" / "git.py"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    contents = "class GitTool:\n" + "\n" * 50 + "    def run(self):\n        pass\n"
    file_path.write_text(contents, encoding="utf-8")
    
    update(file_path, contents)
    entry = lookup(file_path, "UnknownSymbol")
    assert entry is None


def test_cache_miss_triggers_regeneration_from_file_contents(mock_home, dummy_project):
    """get_index regenerates from file contents if cache is missing."""
    file_path = dummy_project / "agentflow" / "tools" / "git.py"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    contents = "class GitTool:\n" + "\n" * 50 + "    def run(self):\n        pass\n"
    file_path.write_text(contents, encoding="utf-8")
    
    # Do not call update manually. get_index should handle it.
    entries = get_index(file_path)
    assert len(entries) == 2
    assert entries[0].name == "GitTool"
    
    # Verify the cache file is now generated
    project_hash = hashlib.sha256(str(dummy_project.resolve()).encode("utf-8")).hexdigest()
    expected_cache_path = mock_home / ".agentflow" / "cache" / project_hash / "index" / "agentflow" / "tools" / "git.py.idx"
    assert expected_cache_path.exists()


def test_update_is_idempotent(mock_home, dummy_project):
    """update running twice produces same result."""
    file_path = dummy_project / "agentflow" / "tools" / "git.py"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    contents = "class GitTool:\n" + "\n" * 50 + "    def run(self):\n        pass\n"
    file_path.write_text(contents, encoding="utf-8")
    
    update(file_path, contents)
    project_hash = hashlib.sha256(str(dummy_project.resolve()).encode("utf-8")).hexdigest()
    expected_cache_path = mock_home / ".agentflow" / "cache" / project_hash / "index" / "agentflow" / "tools" / "git.py.idx"
    mtime1 = expected_cache_path.stat().st_mtime
    
    # Running again should succeed and rewrite/keep the same content
    update(file_path, contents)
    assert expected_cache_path.exists()


def test_cache_path_security_constraint_under_agentflow(mock_home, dummy_project):
    """cache path must resolve under ~/.agentflow/ and outside project tree."""
    file_path = dummy_project / "agentflow" / "tools" / "git.py"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Normally, it is under mock_home/.agentflow and outside project tree
    cache_path = get_cache_path(file_path, dummy_project)
    assert cache_path.is_relative_to(mock_home / ".agentflow")
    
    # If cache_root is mocked to be inside dummy_project, it should raise ValueError
    with patch("pathlib.Path.expanduser", return_value=dummy_project / ".agentflow"):
        with pytest.raises(ValueError, match="cannot resolve under project tree"):
            get_cache_path(file_path, dummy_project)


def test_find_project_root_fallbacks(tmp_path):
    """find_project_root correctly falls back when no project marker is found."""
    # Create directory outside current cwd and without markers
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    
    # Resolves to parent of outside_dir (which is tmp_path) since cwd is not a parent
    root = find_project_root(outside_dir)
    assert root == tmp_path or root == Path.cwd().resolve()


def test_get_cache_path_validation_errors(mock_home, dummy_project, tmp_path):
    """get_cache_path raises ValueErrors when constraints are violated."""
    # 1. Path is not under project root
    outside_file = tmp_path / "outside_file.py"
    with pytest.raises(ValueError, match="is not under project root"):
        get_cache_path(outside_file, dummy_project)
        
    # 2. Cache path doesn't resolve under ~/.agentflow (mock relative_to to fail)
    file_path = dummy_project / "test.py"
    original_relative_to = Path.relative_to
    
    def mock_relative_to(self, other, *args, **kwargs):
        if str(other).endswith(".agentflow") or "invalid_home" in str(other):
            raise ValueError("not relative")
        return original_relative_to(self, other, *args, **kwargs)
        
    with patch.object(Path, "relative_to", mock_relative_to):
        with pytest.raises(ValueError, match="must resolve under"):
            get_cache_path(file_path, dummy_project)


def test_parse_contents_ignored_extension():
    """parse_contents returns [] for ignored file extensions."""
    res = parse_contents(Path("test.txt"), "some content")
    assert res == []


def test_parse_contents_unlink_error():
    """parse_contents survives when temp file unlink raises OSError."""
    # We mock Path.unlink to raise OSError
    with patch("pathlib.Path.unlink", side_effect=OSError("unlink error")):
        res = parse_contents(Path("test.py"), "class A:\n    pass\n" + "\n"*50)
        assert len(res) > 0


def test_get_index_two_args_compatibility(mock_home, dummy_project):
    """get_index handles two-argument (project_root, file_path) signature in both orderings."""
    file_path = dummy_project / "test.py"
    file_path.write_text("class TestClass:\n    pass\n" + "\n" * 50, encoding="utf-8")
    
    # 1. get_index(project_root, file_path)
    entries1 = get_index(dummy_project, file_path)
    assert len(entries1) == 1
    assert entries1[0].name == "TestClass"
    
    # 2. get_index(file_path, project_root)
    entries2 = get_index(file_path, dummy_project)
    assert len(entries2) == 1


def test_get_index_file_io_errors(mock_home, dummy_project):
    """get_index handles file read and OSError cleanly."""
    file_path = dummy_project / "unreadable.py"
    file_path.write_text("class A:\n    pass\n" + "\n" * 50, encoding="utf-8")
    
    # 1. Source file read OSError on cache miss
    with patch("pathlib.Path.read_text", side_effect=OSError("Read error")):
        entries = get_index(file_path)
        assert entries == []  # returns empty list cleanly
        
    # 2. Cache file read OSError
    # Generate cache first
    update(file_path, "class A:\n    pass\n" + "\n" * 50)
    # Mock read_text on cache path to raise OSError
    cache_path = get_cache_path(file_path, dummy_project)
    
    # Patch only when reading the cache path
    orig_read_text = Path.read_text
    def mock_read(self, *args, **kwargs):
        if self == cache_path:
            raise OSError("Cache read error")
        return orig_read_text(self, *args, **kwargs)
        
    with patch("pathlib.Path.read_text", mock_read):
        assert get_index(file_path) == []


def test_get_index_cache_miss_no_source_file(mock_home, dummy_project):
    """get_index handles missing source file on cache miss."""
    file_path = dummy_project / "non_existent_file.py"
    entries = get_index(file_path)
    assert entries == []


def test_get_index_invalid_cache_file_format(mock_home, dummy_project):
    """get_index handles corrupted or invalid lines in cache file."""
    file_path = dummy_project / "corrupt.py"
    file_path.write_text("class A:\n    pass\n" + "\n" * 50, encoding="utf-8")
    
    # Create corrupted cache file manually
    cache_path = get_cache_path(file_path, dummy_project)
    cache_path.write_text("corrupted_line_without_colon\ninvalid:start\ninvalid:1-abc\n", encoding="utf-8")
    
    entries = get_index(file_path)
    assert entries == []


def test_get_index_signature_handling(mock_home, dummy_project):
    """get_index handles various signature reconstruction edge cases."""
    file_path = dummy_project / "bounds.py"
    file_path.write_text("class ClassA:\n    pass\n" + "\n" * 50, encoding="utf-8")
    
    update(file_path, "class ClassA:\n    pass\n" + "\n" * 50)
    # Manually write cache with out of bounds lines
    cache_path = get_cache_path(file_path, dummy_project)
    cache_path.write_text("ClassA:100-105\nClassA.method:110-115\n", encoding="utf-8")
    
    entries = get_index(file_path)
    assert len(entries) == 2
    assert entries[0].name == "ClassA"
    assert entries[0].kind == "function"  # defaults to function when out of bounds
    assert entries[1].name == "ClassA.method"
    assert entries[1].kind == "method"
    assert entries[1].signature is None


def test_update_index_stub(mock_home, dummy_project):
    """update_index writes index to the correct path."""
    file_path = dummy_project / "stub.py"
    contents = "class A:\n    pass\n" + "\n" * 50
    update_index(dummy_project, file_path, contents)
    cache_path = get_cache_path(file_path, dummy_project)
    assert cache_path.exists()
