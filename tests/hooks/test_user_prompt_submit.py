import json
import sys
from io import StringIO
from unittest.mock import patch

import pytest

from agentflow.hooks.user_prompt_submit import main


def _run_with_stdin(prompt_text, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    stdin_data = json.dumps({"prompt": prompt_text})
    monkeypatch.setattr("sys.stdin", StringIO(stdin_data))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    return tmp_path / ".agentflow"


def test_orchestrate_creates_reset_and_removes_signal_files(monkeypatch, tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    (agentflow_dir / "handoff_complete.json").write_text("{}")
    (agentflow_dir / "task_complete.json").write_text("{}")

    result_dir = _run_with_stdin("/orchestrate", monkeypatch, tmp_path)

    assert (result_dir / "reset_accumulator").exists()
    assert not (result_dir / "handoff_complete.json").exists()
    assert not (result_dir / "task_complete.json").exists()


def test_handoff_creates_reset_and_removes_signal_files(monkeypatch, tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    (agentflow_dir / "handoff_complete.json").write_text("{}")

    result_dir = _run_with_stdin("/handoff", monkeypatch, tmp_path)

    assert (result_dir / "reset_accumulator").exists()
    assert not (result_dir / "handoff_complete.json").exists()


def test_non_matching_prompt_does_nothing(monkeypatch, tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    (agentflow_dir / "handoff_complete.json").write_text("{}")

    result_dir = _run_with_stdin("regular user message", monkeypatch, tmp_path)

    assert not (result_dir / "reset_accumulator").exists()
    assert (result_dir / "handoff_complete.json").exists()


def test_signal_files_absent_is_graceful(monkeypatch, tmp_path):
    result_dir = _run_with_stdin("/orchestrate", monkeypatch, tmp_path)

    assert (result_dir / "reset_accumulator").exists()


def test_argv_fallback_when_stdin_is_tty(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.argv", ["hook", "/handoff", "extra"])

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert (tmp_path / ".agentflow" / "reset_accumulator").exists()


def test_empty_prompt_does_nothing(monkeypatch, tmp_path):
    result_dir = _run_with_stdin("", monkeypatch, tmp_path)
    assert not (result_dir / "reset_accumulator").exists()
