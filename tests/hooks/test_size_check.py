"""Tests for T-058: PostToolUse size check hook."""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
import pytest

from agentflow.hooks import size_check


def test_non_py_files_skipped(tmp_path, monkeypatch):
    target = tmp_path / "some_file.txt"
    target.write_text("line\n" * 200)
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))
    with pytest.raises(SystemExit) as exc_info:
        size_check.main()
    assert exc_info.value.code == 0


def test_under_limit_passes(tmp_path, monkeypatch):
    target = tmp_path / "module.py"
    target.write_text("print('hello')\n" * 100)
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))
    with pytest.raises(SystemExit) as exc_info:
        size_check.main()
    assert exc_info.value.code == 0


def test_over_limit_blocks(tmp_path, monkeypatch, capsys):
    target = tmp_path / "module.py"
    target.write_text("print('hello')\n" * 260)
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))
    with pytest.raises(SystemExit) as exc_info:
        size_check.main()
    assert exc_info.value.code == 1
    out = capsys.readouterr().out.strip()
    assert "FILE TOO LARGE" in out
    assert "module.py is 260 lines (limit 250)" in out


def test_tests_limit_correct(tmp_path, monkeypatch, capsys):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    target = tests_dir / "test_module.py"
    
    # 300 lines -> pass
    target.write_text("print('hello')\n" * 300)
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))
    with pytest.raises(SystemExit) as exc_info:
        size_check.main()
    assert exc_info.value.code == 0

    # 360 lines -> fail
    target.write_text("print('hello')\n" * 360)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))
    with pytest.raises(SystemExit) as exc_info:
        size_check.main()
    assert exc_info.value.code == 1
    out = capsys.readouterr().out.strip()
    assert "tests/test_module.py is 360 lines (limit 350)" in out


def test_commands_limit_correct(tmp_path, monkeypatch, capsys):
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()
    target = commands_dir / "command.md"

    # 100 lines -> pass
    target.write_text("line\n" * 100)
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))
    with pytest.raises(SystemExit) as exc_info:
        size_check.main()
    assert exc_info.value.code == 0

    # 160 lines -> fail
    target.write_text("line\n" * 160)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))
    with pytest.raises(SystemExit) as exc_info:
        size_check.main()
    assert exc_info.value.code == 1
    out = capsys.readouterr().out.strip()
    assert "commands/command.md is 160 lines (limit 150)" in out


def test_stub_exemption(tmp_path, monkeypatch):
    target = tmp_path / "module.py"
    lines = ["pass"] * 160 + ["print('hello')"] * 140
    target.write_text("\n".join(lines))
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))
    with pytest.raises(SystemExit) as exc_info:
        size_check.main()
    assert exc_info.value.code == 0


def test_exits_zero_on_invalid_json(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("invalid-json"))
    with pytest.raises(SystemExit) as exc_info:
        size_check.main()
    assert exc_info.value.code == 0


def test_exits_zero_on_missing_file_path(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"tool_input": {}}'))
    with pytest.raises(SystemExit) as exc_info:
        size_check.main()
    assert exc_info.value.code == 0


def test_file_outside_cwd_and_unsupported_extensions(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path / "subdir"))
    
    # outside cwd, but not .py / not commands
    target = tmp_path / "outside.txt"
    target.write_text("hello\n" * 10)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))
    with pytest.raises(SystemExit) as exc_info:
        size_check.main()
    assert exc_info.value.code == 0


def test_exceptions_handled_gracefully(tmp_path, monkeypatch):
    # Triggers OSError in read_text
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": "nonexistent.py"}})))
    with pytest.raises(SystemExit) as exc_info:
        size_check.main()
    assert exc_info.value.code == 0

    # General exception trigger (e.g. read_text raising AttributeError)
    target = tmp_path / "error.py"
    target.write_text("hello")
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: 123)  # splitlines will raise AttributeError
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))
    with pytest.raises(SystemExit) as exc_info:
        size_check.main()
    assert exc_info.value.code == 0
