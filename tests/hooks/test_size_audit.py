"""Tests for T-076: standalone size-limit audit sweep."""

from __future__ import annotations

from agentflow.hooks import size_audit


def test_under_limit_files_not_reported(tmp_path):
    (tmp_path / "module.py").write_text("print('hello')\n" * 100)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_module.py").write_text("print('hello')\n" * 300)
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()
    (commands_dir / "command.md").write_text("line\n" * 100)

    violations = size_audit.audit(tmp_path)

    assert violations == []


def test_implementation_over_limit_detected(tmp_path):
    target = tmp_path / "module.py"
    target.write_text("print('hello')\n" * 260)

    violations = size_audit.audit(tmp_path)

    assert len(violations) == 1
    v = violations[0]
    assert v.path == "module.py"
    assert v.n_lines == 260
    assert v.limit == 250
    assert v.category == "implementation"


def test_tests_over_limit_detected(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    target = tests_dir / "test_module.py"
    target.write_text("print('hello')\n" * 360)

    violations = size_audit.audit(tmp_path)

    assert len(violations) == 1
    v = violations[0]
    assert v.path == "tests/test_module.py"
    assert v.n_lines == 360
    assert v.limit == 350
    assert v.category == "tests"


def test_commands_over_limit_detected(tmp_path):
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()
    target = commands_dir / "command.md"
    target.write_text("line\n" * 160)

    violations = size_audit.audit(tmp_path)

    assert len(violations) == 1
    v = violations[0]
    assert v.path == "commands/command.md"
    assert v.n_lines == 160
    assert v.limit == 150
    assert v.category == "commands"


def test_stub_files_exempt(tmp_path):
    target = tmp_path / "module.py"
    lines = ["pass"] * 160 + ["print('hello')"] * 140
    target.write_text("\n".join(lines))

    violations = size_audit.audit(tmp_path)

    assert violations == []


def test_non_py_non_commands_files_skipped(tmp_path):
    target = tmp_path / "some_file.txt"
    target.write_text("line\n" * 500)

    violations = size_audit.audit(tmp_path)

    assert violations == []


def test_multiple_violations_across_categories(tmp_path):
    (tmp_path / "module.py").write_text("print('hello')\n" * 260)

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_module.py").write_text("print('hello')\n" * 360)

    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()
    (commands_dir / "command.md").write_text("line\n" * 160)

    (tmp_path / "ok_module.py").write_text("print('hello')\n" * 10)

    violations = size_audit.audit(tmp_path)

    paths = {v.path for v in violations}
    assert paths == {"module.py", "tests/test_module.py", "commands/command.md"}


def test_empty_file_not_reported(tmp_path):
    (tmp_path / "empty.py").write_text("")

    violations = size_audit.audit(tmp_path)

    assert violations == []


def test_main_prints_violations_and_exits_nonzero(tmp_path, capsys, monkeypatch):
    target = tmp_path / "module.py"
    target.write_text("print('hello')\n" * 260)

    import pytest

    with pytest.raises(SystemExit) as exc_info:
        size_audit.main([str(tmp_path)])

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "module.py" in captured.out
    assert "260" in captured.out
    assert "250" in captured.out


def test_main_exits_zero_when_no_violations(tmp_path):
    (tmp_path / "module.py").write_text("print('hello')\n" * 10)

    import pytest

    with pytest.raises(SystemExit) as exc_info:
        size_audit.main([str(tmp_path)])

    assert exc_info.value.code == 0
