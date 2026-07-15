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
    test_sid = "test-session-abc"
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", test_sid)
    hc_file = agentflow_dir / f"handoff_complete_{test_sid}.json"
    hc_file.write_text("{}")
    (agentflow_dir / "task_complete.json").write_text("{}")

    result_dir = _run_with_stdin("/orchestrate", monkeypatch, tmp_path)

    # T-209: reset_accumulator no longer written (dead artifact)
    assert not (result_dir / "reset_accumulator").exists()
    assert not hc_file.exists()
    assert not (result_dir / "task_complete.json").exists()


def test_handoff_creates_reset_and_removes_signal_files(monkeypatch, tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    test_sid = "test-session-abc"
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", test_sid)
    hc_file = agentflow_dir / f"handoff_complete_{test_sid}.json"
    hc_file.write_text("{}")

    result_dir = _run_with_stdin("/handoff", monkeypatch, tmp_path)

    # T-209: reset_accumulator no longer written
    assert not (result_dir / "reset_accumulator").exists()
    assert not hc_file.exists()


def test_non_matching_prompt_does_nothing(monkeypatch, tmp_path):
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    test_sid = "test-session-abc"
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", test_sid)
    hc_file = agentflow_dir / f"handoff_complete_{test_sid}.json"
    hc_file.write_text("{}")

    result_dir = _run_with_stdin("regular user message", monkeypatch, tmp_path)

    assert not (result_dir / "reset_accumulator").exists()
    assert hc_file.exists()


def test_signal_files_absent_is_graceful(monkeypatch, tmp_path):
    result_dir = _run_with_stdin("/orchestrate", monkeypatch, tmp_path)

    # T-209: reset_accumulator no longer written — graceful when signal files absent
    assert not (result_dir / "reset_accumulator").exists()


def test_argv_fallback_when_stdin_is_tty(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.argv", ["hook", "/handoff", "extra"])

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    # T-209: reset_accumulator no longer written
    assert not (tmp_path / ".agentflow" / "reset_accumulator").exists()


def test_empty_prompt_does_nothing(monkeypatch, tmp_path):
    result_dir = _run_with_stdin("", monkeypatch, tmp_path)
    assert not (result_dir / "reset_accumulator").exists()


def test_orchestrate_writes_session_state_json(monkeypatch, tmp_path):
    """When /orchestrate is in prompt (without sid), write session_state.json with orchestrator type."""
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
    agentflow_dir = _run_with_stdin("/orchestrate", monkeypatch, tmp_path)
    session_state_file = agentflow_dir / "session_state.json"
    assert session_state_file.exists()
    data = json.loads(session_state_file.read_text("utf-8"))
    assert data == {"session_type": "orchestrator"}


def test_oracle_writes_session_state_json(monkeypatch, tmp_path):
    """When /oracle is in prompt (without sid), write session_state.json with oracle type."""
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
    agentflow_dir = _run_with_stdin("/oracle", monkeypatch, tmp_path)
    session_state_file = agentflow_dir / "session_state.json"
    assert session_state_file.exists()
    data = json.loads(session_state_file.read_text("utf-8"))
    assert data == {"session_type": "oracle"}


def test_non_matching_prompt_no_session_state(monkeypatch, tmp_path):
    """When prompt doesn't match /orchestrate or /oracle, don't create session_state.json."""
    agentflow_dir = _run_with_stdin("regular message", monkeypatch, tmp_path)
    session_state_file = agentflow_dir / "session_state.json"
    assert not session_state_file.exists()


def test_handoff_does_not_write_session_state(monkeypatch, tmp_path):
    """/handoff should not create session_state.json (only /orchestrate and /oracle do)."""
    agentflow_dir = _run_with_stdin("/handoff", monkeypatch, tmp_path)
    session_state_file = agentflow_dir / "session_state.json"
    assert not session_state_file.exists()
    # T-209: reset_accumulator no longer written
    assert not (agentflow_dir / "reset_accumulator").exists()


def test_cleanup_merged_in_flight_marks_complete_and_removes(monkeypatch, tmp_path):
    """When task_prs.json has URL and PR is MERGED, task removed from tasks_in_flight."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    # Write tasks_in_flight.json with T-001
    in_flight_file = agentflow_dir / "tasks_in_flight.json"
    in_flight_file.write_text(json.dumps(["T-001"]))

    # Write task_prs.json with T-001 -> URL mapping
    prs_file = agentflow_dir / "task_prs.json"
    prs_file.write_text(json.dumps({"T-001": "https://github.com/owner/repo/pull/123"}))

    # Write tasks.json with T-001 as pending
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-001", "status": "pending"}]}))

    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.argv", ["hook"])

    # Mock _check_pr_state to return "MERGED"
    with patch("agentflow.hooks.user_prompt_submit._check_pr_state", return_value="MERGED"):
        with patch("agentflow.hooks.user_prompt_submit._mark_task_complete", return_value=True):
            with patch("agentflow.hooks.user_prompt_submit._run_cleanup"):
                with pytest.raises(SystemExit) as exc:
                    main()

    assert exc.value.code == 0

    # Verify T-001 removed from tasks_in_flight.json
    remaining = json.loads(in_flight_file.read_text())
    assert "T-001" not in remaining


def test_cleanup_merged_in_flight_uses_title_fallback(monkeypatch, tmp_path):
    """When no task_prs.json, use merged PR title fallback (prefix match on task_id)."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    # Write tasks_in_flight.json with T-001
    in_flight_file = agentflow_dir / "tasks_in_flight.json"
    in_flight_file.write_text(json.dumps(["T-001"]))

    # No task_prs.json

    # Write tasks.json with T-001 as pending
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps({"tasks": [{"task_id": "T-001", "status": "pending"}]}))

    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.argv", ["hook"])

    # Mock _fetch_merged_pr_titles to return a title with task_id: prefix (matching expected format)
    with patch("agentflow.hooks.user_prompt_submit._fetch_merged_pr_titles", return_value={"T-001: feature description"}):
        with patch("agentflow.hooks.user_prompt_submit._mark_task_complete", return_value=True):
            with patch("agentflow.hooks.user_prompt_submit._run_cleanup"):
                with pytest.raises(SystemExit) as exc:
                    main()

    assert exc.value.code == 0

    # Verify T-001 removed from tasks_in_flight.json
    remaining = json.loads(in_flight_file.read_text())
    assert "T-001" not in remaining


def test_cleanup_merged_in_flight_skips_when_no_in_flight_file(monkeypatch, tmp_path):
    """When tasks_in_flight.json absent, cleanup runs silently with no errors."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    # No tasks_in_flight.json

    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.argv", ["hook"])

    # Should exit without error
    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 0


def test_orchestrate_writes_sid_keyed_session_state_when_sid_set(monkeypatch, tmp_path):
    """When AGENTFLOW_SESSION_ID=abc123 and /orchestrate, write to sessions/abc123/session_state.json."""
    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "abc123")
    agentflow_dir = _run_with_stdin("/orchestrate", monkeypatch, tmp_path)

    # Should write to sessions/<sid>/ directory
    sid_keyed_file = agentflow_dir / "sessions" / "abc123" / "session_state.json"
    assert sid_keyed_file.exists()
    data = json.loads(sid_keyed_file.read_text("utf-8"))
    assert data == {"session_type": "orchestrator"}

    # Should NOT write to unkeyed file
    unkeyed_file = agentflow_dir / "session_state.json"
    assert not unkeyed_file.exists()


def test_orchestrate_writes_unkeyed_session_state_when_no_sid(monkeypatch, tmp_path):
    """When no AGENTFLOW_SESSION_ID and /orchestrate, write to session_state.json."""
    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    # Explicitly unset AGENTFLOW_SESSION_ID if present
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)

    agentflow_dir = _run_with_stdin("/orchestrate", monkeypatch, tmp_path)

    # Should write to unkeyed file
    unkeyed_file = agentflow_dir / "session_state.json"
    assert unkeyed_file.exists()
    data = json.loads(unkeyed_file.read_text("utf-8"))
    assert data == {"session_type": "orchestrator"}


def test_oracle_writes_sid_keyed_session_state(monkeypatch, tmp_path):
    """When /oracle with AGENTFLOW_SESSION_ID, write to sessions/<sid>/session_state.json with oracle type."""
    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "xyz789")

    agentflow_dir = _run_with_stdin("/oracle", monkeypatch, tmp_path)

    # Should write to sessions/<sid>/ directory
    sid_keyed_file = agentflow_dir / "sessions" / "xyz789" / "session_state.json"
    assert sid_keyed_file.exists()
    data = json.loads(sid_keyed_file.read_text("utf-8"))
    assert data == {"session_type": "oracle"}


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
