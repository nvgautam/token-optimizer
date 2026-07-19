"""Tests for T-058: PostToolUse size check hook."""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch
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
    captured = capsys.readouterr()
    out = (captured.out + captured.err).strip()
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
    captured = capsys.readouterr()
    out = (captured.out + captured.err).strip()
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
    captured = capsys.readouterr()
    out = (captured.out + captured.err).strip()
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


def test_outputs_go_to_stderr(tmp_path, monkeypatch, capsys):
    target = tmp_path / "module.py"
    target.write_text("print('hello')\n" * 260)
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))
    with pytest.raises(SystemExit) as exc_info:
        size_check.main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "FILE TOO LARGE" in captured.err
    assert captured.out == ""


def test_size_check_logs_violation(tmp_path, monkeypatch):
    """On blocked write (n_lines > limit), appends to size_violations.jsonl."""
    target = tmp_path / "module.py"
    target.write_text("print('hello')\n" * 260)
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))

    with pytest.raises(SystemExit) as exc_info:
        size_check.main()
    assert exc_info.value.code == 1

    violations_path = tmp_path / ".agentflow" / "size_violations.jsonl"
    assert violations_path.exists(), "size_violations.jsonl not created"
    entry = json.loads(violations_path.read_text().strip())
    assert "module.py" in entry["file"]
    assert entry["blocked_lines"] == 260
    assert entry["actual_lines"] == 260
    assert entry["limit"] == 250
    assert "ts" in entry


class TestDedupeGuard:
    def test_dedupe_guard_not_filed(self, tmp_path, monkeypatch):
        target = tmp_path / "module.py"
        target.write_text("print('hello')\n" * 260)
        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))

        with pytest.raises(SystemExit) as exc_info:
            size_check.main()
        assert exc_info.value.code == 1

        violations_path = tmp_path / ".agentflow" / "size_violations.jsonl"
        assert violations_path.exists()
        assert "module.py" in violations_path.read_text()

    def test_dedupe_guard_filed_in_tasks_json(self, tmp_path, monkeypatch):
        target = tmp_path / "module.py"
        target.write_text("print('hello')\n" * 260)
        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))

        # Write to tasks.json
        tasks_json = tmp_path / "tasks.json"
        tasks_json.write_text(json.dumps({
            "tasks": [
                {"task_id": "T-100", "status": "pending", "owns": ["module.py"]}
            ]
        }))

        with pytest.raises(SystemExit) as exc_info:
            size_check.main()
        assert exc_info.value.code == 1

        violations_path = tmp_path / ".agentflow" / "size_violations.jsonl"
        assert not violations_path.exists()

    def test_dedupe_guard_filed_in_archive(self, tmp_path, monkeypatch):
        target = tmp_path / "module.py"
        target.write_text("print('hello')\n" * 260)
        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))

        # Create .agentflow/tasks.archive.json
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        archive_json = agentflow_dir / "tasks.archive.json"
        archive_json.write_text(json.dumps([
            {"task_id": "T-100", "status": "complete", "title": "Split module.py"}
        ]))

        with pytest.raises(SystemExit) as exc_info:
            size_check.main()
        assert exc_info.value.code == 1

        violations_path = tmp_path / ".agentflow" / "size_violations.jsonl"
        assert not violations_path.exists()

    def test_dedupe_guard_filed_in_execution_plan(self, tmp_path, monkeypatch):
        target = tmp_path / "module.py"
        target.write_text("print('hello')\n" * 260)
        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))

        # Write execution_plan.md
        plan_md = tmp_path / "execution_plan.md"
        plan_md.write_text("Addendum: T-100 - Split module.py")

        with pytest.raises(SystemExit) as exc_info:
            size_check.main()
        assert exc_info.value.code == 1

        violations_path = tmp_path / ".agentflow" / "size_violations.jsonl"
        assert not violations_path.exists()

    def test_is_task_filed_relative_to_value_error(self, tmp_path, monkeypatch):
        target = tmp_path / "module.py"
        target.write_text("print('hello')\n" * 260)
        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path / "other_subdir"))
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))

        (tmp_path / "other_subdir").mkdir(parents=True, exist_ok=True)
        plan_md = tmp_path / "other_subdir" / "execution_plan.md"
        plan_md.write_text("Addendum: T-100 - Split module.py")

        with pytest.raises(SystemExit) as exc_info:
            size_check.main()
        assert exc_info.value.code == 1

        violations_path = tmp_path / "other_subdir" / ".agentflow" / "size_violations.jsonl"
        assert not violations_path.exists()

    def test_corrupted_json_in_tasks_and_archive(self, tmp_path, monkeypatch):
        target = tmp_path / "module.py"
        target.write_text("print('hello')\n" * 260)
        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))

        # Write invalid JSON to tasks.json
        (tmp_path / "tasks.json").write_text("{invalid json}")

        # Write invalid JSON to tasks.archive.json
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        (agentflow_dir / "tasks.archive.json").write_text("{invalid json}")

        with pytest.raises(SystemExit) as exc_info:
            size_check.main()
        assert exc_info.value.code == 1
        assert (agentflow_dir / "size_violations.jsonl").exists()

    def test_size_violations_write_error(self, tmp_path, monkeypatch, capsys):
        target = tmp_path / "module.py"
        target.write_text("print('hello')\n" * 260)
        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))

        # Mock mkdir to raise an exception
        with patch("pathlib.Path.mkdir", side_effect=OSError("mkdir failed")):
            with pytest.raises(SystemExit) as exc_info:
                size_check.main()
            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "violations_write_error" in captured.err
