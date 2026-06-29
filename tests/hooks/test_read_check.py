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
