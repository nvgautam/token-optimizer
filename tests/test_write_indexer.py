"""Tests for agentflow/hooks/write_indexer.py (T-046)."""

import io
import json
import sys
from pathlib import Path
from unittest.mock import call, patch

import pytest

import agentflow.hooks.write_indexer as hook_module


def _stdin(tool_name: str, file_path: str) -> io.StringIO:
    return io.StringIO(json.dumps({"tool_name": tool_name, "tool_input": {"file_path": file_path}}))


def _py_content(n: int = 60) -> str:
    return "\n".join(f"# line {i}" for i in range(n))


def _md_content(n: int = 60) -> str:
    lines = []
    for i in range(n):
        lines.append(f"## Section {i}" if i % 10 == 0 else f"content {i}")
    return "\n".join(lines)


def _run_main(stdin: io.StringIO) -> int:
    with patch("sys.stdin", stdin):
        with pytest.raises(SystemExit) as exc:
            hook_module.main()
    return exc.value.code


def test_write_py_file_regenerates_idx(tmp_path):
    p = tmp_path / "sample.py"
    p.write_text(_py_content(60))
    with patch("agentflow.indexer.index_manager.update") as mock_update:
        code = _run_main(_stdin("Write", str(p)))
    assert code == 0
    mock_update.assert_called_once_with(p, _py_content(60))


def test_write_md_file_regenerates_idx(tmp_path):
    p = tmp_path / "sample.md"
    content = _md_content(60)
    p.write_text(content)
    with patch("agentflow.indexer.index_manager.update") as mock_update:
        code = _run_main(_stdin("Write", str(p)))
    assert code == 0
    mock_update.assert_called_once_with(p, content)


def test_edit_triggers_idx_regeneration(tmp_path):
    p = tmp_path / "sample.py"
    p.write_text(_py_content(60))
    with patch("agentflow.indexer.index_manager.update") as mock_update:
        code = _run_main(_stdin("Edit", str(p)))
    assert code == 0
    mock_update.assert_called_once()


def test_skips_files_under_50_lines(tmp_path):
    p = tmp_path / "short.py"
    p.write_text(_py_content(30))
    with patch("agentflow.indexer.index_manager.update") as mock_update:
        code = _run_main(_stdin("Write", str(p)))
    assert code == 0
    mock_update.assert_not_called()


def test_skips_non_py_md_files(tmp_path):
    for name in ("data.json", "config.yaml", "notes.txt"):
        p = tmp_path / name
        p.write_text("x\n" * 60)
        with patch("agentflow.indexer.index_manager.update") as mock_update:
            code = _run_main(_stdin("Write", str(p)))
        assert code == 0
        mock_update.assert_not_called()


def test_exits_zero_silently(tmp_path, capsys):
    p = tmp_path / "sample.py"
    p.write_text(_py_content(60))
    with patch("agentflow.indexer.index_manager.update") as mock_update:
        code = _run_main(_stdin("Write", str(p)))
    assert code == 0
    mock_update.assert_called_once_with(p, _py_content(60))
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_exits_zero_on_bad_stdin():
    code = _run_main(io.StringIO("not-json"))
    assert code == 0


def test_exits_zero_on_missing_file_path():
    stdin = io.StringIO(json.dumps({"tool_name": "Write", "tool_input": {}}))
    code = _run_main(stdin)
    assert code == 0


def test_idempotent(tmp_path):
    p = tmp_path / "sample.py"
    p.write_text(_py_content(60))
    results = []
    for _ in range(2):
        with patch("agentflow.indexer.index_manager.update") as mock_update:
            _run_main(_stdin("Write", str(p)))
            results.append(mock_update.call_args)
    assert results[0] == results[1]
