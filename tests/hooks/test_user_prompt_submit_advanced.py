import json
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


def test_clear_creates_clear_signal(monkeypatch, tmp_path):
    """Submitting /clear writes .agentflow/clear_signal and NOT reset_accumulator."""
    agentflow_dir = _run_with_stdin("/clear", monkeypatch, tmp_path)

    # Should write clear_signal file
    assert (agentflow_dir / "clear_signal").exists()

    # Should NOT write reset_accumulator (that's only for /orchestrate and /handoff)
    assert not (agentflow_dir / "reset_accumulator").exists()


def test_clear_does_not_write_session_state(monkeypatch, tmp_path):
    """Submitting /clear does not write session_state.json."""
    agentflow_dir = _run_with_stdin("/clear", monkeypatch, tmp_path)

    # Should not write session_state.json (that's only for /orchestrate and /oracle)
    assert not (agentflow_dir / "session_state.json").exists()

    # But should write clear_signal
    assert (agentflow_dir / "clear_signal").exists()


def test_clear_text_in_message_does_not_write_signal(monkeypatch, tmp_path):
    """A prompt that mentions '/clear' in prose does NOT write clear_signal."""
    agentflow_dir = _run_with_stdin("how does /clear work?", monkeypatch, tmp_path)

    # Substring match must not fire — clear_signal must not be created
    assert not (agentflow_dir / "clear_signal").exists()


def test_read_session_state_uses_sid_scoped_path(monkeypatch, tmp_path, capsys):
    """T-224: session_type read uses sessions/<sid>/session_state.json, not flat+keyed path."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    test_sid = "read-test-sid"
    # Write session_state.json to the SID-scoped path (matches write path)
    sid_dir = agentflow_dir / "sessions" / test_sid
    sid_dir.mkdir(parents=True)
    (sid_dir / "session_state.json").write_text(json.dumps({"session_type": "orchestrator"}))

    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", test_sid)
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps({"prompt": "regular message"})))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    with pytest.raises(SystemExit):
        main()

    captured = capsys.readouterr()
    assert "[SESSION: orchestrator]" in captured.out


def test_reset_accumulator_not_written(monkeypatch, tmp_path):
    """T-209: reset_file.touch() removed — reset_accumulator is never written."""
    result_dir = _run_with_stdin("/orchestrate", monkeypatch, tmp_path)
    assert not (result_dir / "reset_accumulator").exists()

    result_dir2 = _run_with_stdin("/handoff", monkeypatch, tmp_path)
    assert not (result_dir2 / "reset_accumulator").exists()


def test_orchestrate_substring_does_not_trigger_session_type(monkeypatch, tmp_path):
    """T-292: substring match '/orchestrate' in text should not trigger orchestrator session_type."""
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
    agentflow_dir = _run_with_stdin("Read more about /orchestrate in the docs", monkeypatch, tmp_path)
    session_state_file = agentflow_dir / "session_state.json"
    # Should NOT create session_state.json for substring match
    assert not session_state_file.exists()


def test_oracle_substring_does_not_trigger_session_type(monkeypatch, tmp_path):
    """T-292: substring match '/oracle' in text should not trigger oracle session_type."""
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
    agentflow_dir = _run_with_stdin("Learn about /oracle skill", monkeypatch, tmp_path)
    session_state_file = agentflow_dir / "session_state.json"
    # Should NOT create session_state.json for substring match
    assert not session_state_file.exists()
