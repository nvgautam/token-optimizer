"""Tests for T-054: PreToolUse Read hook — enforcement mode."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import io
from pathlib import Path
import pytest
from agentflow.hooks import read_check

HOOK = Path(__file__).parent.parent.parent / "agentflow" / "hooks" / "read_check.py"


def _run(payload: dict, cwd: str | None = None, home: str | None = None) -> tuple[int, str]:
    env = {**os.environ}
    if home:
        env["HOME"] = home
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )
    return result.returncode, result.stdout.strip()


def _make_idx(home: Path, cwd: str, rel: str) -> None:
    cwd_hash = hashlib.sha256(cwd.encode()).hexdigest()
    idx_path = home / ".agentflow" / "cache" / cwd_hash / "index" / f"{rel}.idx"
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    idx_path.write_text("some_func:1-10\n")


def test_silent_when_offset_already_set(tmp_path):
    payload = {"tool_name": "Read", "tool_input": {"file_path": "/some/file.py", "offset": 5}}
    code, out = _run(payload, cwd=str(tmp_path))
    assert code == 0
    assert out == ""


def test_silent_when_file_path_missing(tmp_path):
    payload = {"tool_name": "Read", "tool_input": {}}
    code, out = _run(payload, cwd=str(tmp_path))
    assert code == 0
    assert out == ""


def test_silent_when_idx_absent(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    target = project / "module.py"
    target.write_text("# code")
    payload = {"tool_name": "Read", "tool_input": {"file_path": str(target)}}
    code, out = _run(payload, cwd=str(project), home=str(home))
    assert code == 0
    assert out == ""


def test_blocks_when_idx_exists(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    target = project / "module.py"
    target.write_text("# code")
    _make_idx(home, str(project), "module.py")
    payload = {"tool_name": "Read", "tool_input": {"file_path": str(target)}}
    code, out = _run(payload, cwd=str(project), home=str(home))
    assert code == 2
    assert out != ""
    assert "module.py" in out
    assert "Read(offset=" in out


def test_hint_output_is_opaque(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    target = project / "module.py"
    target.write_text("# code")
    _make_idx(home, str(project), "module.py")
    payload = {"tool_name": "Read", "tool_input": {"file_path": str(target)}}
    _, out = _run(payload, cwd=str(project), home=str(home))
    low = out.lower()
    for word in ("index", ".idx", "symbol", "token"):
        assert word not in low, f"Forbidden word '{word}' found in output: {out!r}"


def test_exits_zero_on_invalid_json(tmp_path):
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input="not-json",
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0


def test_exits_zero_when_file_outside_cwd(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    payload = {"tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}}
    code, out = _run(payload, cwd=str(project), home=str(home))
    assert code == 0
    assert out == ""


def test_silent_when_offset_is_zero(tmp_path):
    payload = {"tool_name": "Read", "tool_input": {"file_path": "/some/file.py", "offset": 0}}
    code, out = _run(payload, cwd=str(tmp_path))
    assert code == 0
    assert out == ""


def test_empty_idx_allows_read(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    target = project / "module.py"
    target.write_text("# code")
    
    cwd_hash = hashlib.sha256(str(project).encode()).hexdigest()
    idx_path = home / ".agentflow" / "cache" / cwd_hash / "index" / "module.py.idx"
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    idx_path.write_text("   \n  ")
    
    payload = {"tool_name": "Read", "tool_input": {"file_path": str(target)}}
    code, out = _run(payload, cwd=str(project), home=str(home))
    assert code == 0
    assert out == ""


def test_output_is_single_line_and_no_forbidden_words(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    target = project / "module.py"
    target.write_text("# code")
    _make_idx(home, str(project), "module.py")
    payload = {"tool_name": "Read", "tool_input": {"file_path": str(target)}}
    code, out = _run(payload, cwd=str(project), home=str(home))
    assert code == 2
    assert "\n" not in out
    assert "module.py" in out
    assert "Read(offset=" in out
    low = out.lower()
    for word in ("index", ".idx", "symbol", "token"):
        assert word not in low


def test_in_process_all_branches(tmp_path, monkeypatch, capsys):
    # Test JSON decode error
    monkeypatch.setattr(sys, "stdin", io.StringIO("invalid-json"))
    with pytest.raises(SystemExit) as exc_info:
        read_check.main()
    assert exc_info.value.code == 0

    # Test file_path missing
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"tool_input": {}}'))
    with pytest.raises(SystemExit) as exc_info:
        read_check.main()
    assert exc_info.value.code == 0

    # Test offset present
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"tool_input": {"file_path": "/some/file.py", "offset": 5}}'))
    with pytest.raises(SystemExit) as exc_info:
        read_check.main()
    assert exc_info.value.code == 0

    # Test path outside cwd
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(os, "getcwd", lambda: str(project))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": "/outside/file.py"}})))
    with pytest.raises(SystemExit) as exc_info:
        read_check.main()
    assert exc_info.value.code == 0

    # Test idx file absent
    target = project / "module.py"
    target.write_text("# code")
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))
    with pytest.raises(SystemExit) as exc_info:
        read_check.main()
    assert exc_info.value.code == 0

    # Test idx file exists but empty
    cwd_hash = hashlib.sha256(str(project).encode()).hexdigest()
    idx_path = home / ".agentflow" / "cache" / cwd_hash / "index" / "module.py.idx"
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    idx_path.write_text("   \n ")
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))
    with pytest.raises(SystemExit) as exc_info:
        read_check.main()
    assert exc_info.value.code == 0

    # Test idx file exists and not empty
    idx_path.write_text("some_func:1-10\n")
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}})))
    with pytest.raises(SystemExit) as exc_info:
        read_check.main()
    assert exc_info.value.code == 2
    out = capsys.readouterr().out.strip()
    assert "\n" not in out
    assert "module.py" in out
    assert "Read(offset=" in out


def test_new_logic_subprocess(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    target = project / "module.py"
    target.write_text("\n" * 100)
    _make_idx(home, str(project), "module.py")

    # exit 1 on large-range
    payload = {"tool_name": "Read", "tool_input": {"file_path": str(target), "offset": 0, "limit": 80}}
    code, out = _run(payload, cwd=str(project), home=str(home))
    assert code == 1
    assert "Large-range read (80/100 lines, 80%)" in out

    # exit 0 on targeted read
    payload["tool_input"]["limit"] = 20
    code, out = _run(payload, cwd=str(project), home=str(home))
    assert code == 0

    # exit 0 on small file
    target.write_text("\n" * 40)
    payload["tool_input"]["limit"] = 35
    code, out = _run(payload, cwd=str(project), home=str(home))
    assert code == 0

    # exit 0 on no idx
    target.write_text("\n" * 100)
    no_idx_project = tmp_path / "no_idx"
    no_idx_project.mkdir()
    target_no_idx = no_idx_project / "module.py"
    target_no_idx.write_text("\n" * 100)
    payload["tool_input"]["file_path"] = str(target_no_idx)
    code, out = _run(payload, cwd=str(no_idx_project), home=str(home))
    assert code == 0


def test_in_process_new_logic(tmp_path, monkeypatch, capsys):
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(os, "getcwd", lambda: str(project))
    target = project / "module.py"
    target.write_text("\n" * 100)

    cwd_hash = hashlib.sha256(str(project).encode()).hexdigest()
    idx_path = home / ".agentflow" / "cache" / cwd_hash / "index" / "module.py.idx"
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    idx_path.write_text("some_func:1-10\n")

    def run_assert(payload, expected_code):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        with pytest.raises(SystemExit) as exc_info:
            read_check.main()
        assert exc_info.value.code == expected_code

    # 1. Exit 1 on large-range read with idx
    run_assert({"tool_input": {"file_path": str(target), "offset": 0, "limit": 80}}, 1)
    assert "Large-range read (80/100 lines, 80%)" in capsys.readouterr().out

    # 2. Exit 0 on targeted read
    run_assert({"tool_input": {"file_path": str(target), "offset": 0, "limit": 20}}, 0)

    # 3. Small file
    small = project / "small.py"
    small.write_text("\n" * 40)
    (idx_path.parent / "small.py.idx").write_text("some_func:1-10\n")
    run_assert({"tool_input": {"file_path": "small.py", "offset": 0, "limit": 35}}, 0)

    # 4. No idx exists
    no_idx = project / "no_idx.py"
    no_idx.write_text("\n" * 100)
    run_assert({"tool_input": {"file_path": str(no_idx), "offset": 0, "limit": 80}}, 0)

    # 5. Config threshold
    monkeypatch.setenv("AGENTFLOW_READ_COVERAGE_THRESHOLD", "0.90")
    run_assert({"tool_input": {"file_path": str(target), "offset": 0, "limit": 80}}, 0)

    monkeypatch.setenv("AGENTFLOW_READ_COVERAGE_THRESHOLD", "0.30")
    run_assert({"tool_input": {"file_path": str(target), "offset": 0, "limit": 40}}, 1)
    assert "Large-range read (40/100 lines, 40%)" in capsys.readouterr().out

    monkeypatch.setenv("AGENTFLOW_READ_COVERAGE_THRESHOLD", "invalid")
    run_assert({"tool_input": {"file_path": str(target), "offset": 0, "limit": 80}}, 1)
    capsys.readouterr()

    # 6. Cover missing branches (line 41 empty sections, line 83 only offset present)
    empty_idx = project / "empty.py"
    empty_idx.write_text("\n" * 100)
    (idx_path.parent / "empty.py.idx").write_text("")
    run_assert({"tool_input": {"file_path": str(empty_idx), "offset": 0, "limit": 80}}, 0)

    run_assert({"tool_input": {"file_path": str(target), "offset": 5}}, 0)

    # Invalid limit/offset types
    run_assert({"tool_input": {"file_path": str(target), "offset": "invalid", "limit": 80}}, 0)

    # File read error
    (idx_path.parent / "nonexistent.py.idx").write_text("some_func:1-10\n")
    run_assert({"tool_input": {"file_path": "nonexistent.py", "offset": 0, "limit": 80}}, 0)

