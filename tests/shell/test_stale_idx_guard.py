# Tests for stale index guard
import os
import time
from unittest.mock import patch
import pytest
from agentflow.shell.session_manager import SessionManager

class FakePTY:
    def __init__(self):
        self._on_output = None
        self._on_exit = None
        self.inputs = []
    def write_input(self, text: str) -> None:
        self.inputs.append(text)
    def read_output(self, timeout: float = 1.0) -> bytes:
        return b""

class FakeTokenizer:
    def count_tokens(self, text: str, provider: str = "claude") -> int:
        return 1
    def accumulate(self, text: str, provider: str = "claude") -> int:
        return 1

@pytest.fixture
def temp_project(tmp_path, monkeypatch):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").touch()
    py_file = project_dir / "src.py"
    py_file.write_text("class Test:\n" + "\n" * 55, encoding="utf-8")
    md_file = project_dir / "doc.md"
    md_file.write_text("# Doc\n" + "\n" * 55, encoding="utf-8")
    monkeypatch.chdir(project_dir)
    return project_dir, home_dir

def test_stale_idx_guard_on_start(temp_project):
    project_dir, home_dir = temp_project
    pty = FakePTY()
    tok = FakeTokenizer()
    with patch("subprocess.run") as mock_run:
        SessionManager(pty, tok, config={})
        assert mock_run.called
        args = mock_run.call_args[0][0]
        assert "write_indexer.py" in args[1]
        assert any("src.py" in a for a in args)
        assert any("doc.md" in a for a in args)

def test_stale_idx_guard_stale_detection(temp_project):
    project_dir, home_dir = temp_project
    import hashlib
    h = hashlib.sha256(str(project_dir.resolve()).encode()).hexdigest()
    cache_dir = home_dir / ".agentflow" / "cache" / h / "index"
    cache_dir.mkdir(parents=True)
    py_idx = cache_dir / "src.py.idx"
    py_idx.write_text("Test:1-60\n", encoding="utf-8")
    os.utime(py_idx, (time.time() - 100, time.time() - 100))
    pty = FakePTY()
    tok = FakeTokenizer()
    with patch("subprocess.run") as mock_run:
        SessionManager(pty, tok, config={})
        assert mock_run.called
        args = mock_run.call_args[0][0]
        assert any("src.py" in a for a in args)

def test_write_indexer_cli_mode(temp_project):
    project_dir, home_dir = temp_project
    py_large = project_dir / "large.py"
    py_large.write_text("class TargetClass:\n" + "\n" * 50 + "    def test_method(self):\n        pass\n", encoding="utf-8")
    
    from agentflow.hooks.write_indexer import main as hook_main
    
    # Positive case
    with patch("sys.argv", ["write_indexer.py", str(py_large)]), patch("agentflow.indexer.index_manager.update") as mock_update:
        with pytest.raises(SystemExit) as exc:
            hook_main()
        assert exc.value.code == 0
        mock_update.assert_called_once_with(py_large, py_large.read_text(encoding="utf-8"))

    # Ineligible suffix
    txt_file = project_dir / "large.txt"
    txt_file.write_text("class TargetClass:\n" + "\n" * 50, encoding="utf-8")
    with patch("sys.argv", ["write_indexer.py", str(txt_file)]), patch("agentflow.indexer.index_manager.update") as mock_update:
        with pytest.raises(SystemExit) as exc:
            hook_main()
        assert exc.value.code == 0
        mock_update.assert_not_called()

    # Short file
    short_file = project_dir / "short.py"
    short_file.write_text("def test():\n    pass\n", encoding="utf-8")
    with patch("sys.argv", ["write_indexer.py", str(short_file)]), patch("agentflow.indexer.index_manager.update") as mock_update:
        with pytest.raises(SystemExit) as exc:
            hook_main()
        assert exc.value.code == 0
        mock_update.assert_not_called()

    # OSError reading file
    with patch("sys.argv", ["write_indexer.py", str(py_large)]), patch("agentflow.hooks.write_indexer.Path.read_text", side_effect=OSError("read error")), patch("agentflow.indexer.index_manager.update") as mock_update:
        with pytest.raises(SystemExit) as exc:
            hook_main()
        assert exc.value.code == 0
        mock_update.assert_not_called()
