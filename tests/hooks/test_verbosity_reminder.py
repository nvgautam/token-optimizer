import pytest
from unittest.mock import patch
from agentflow.hooks.verbosity_reminder import main

def test_verbosity_reminder_counter_increments_and_creates_file(tmp_path, capsys):
    counter_file = tmp_path / "verbosity_turn_counter"
    assert not counter_file.exists()

    with patch("agentflow.hooks.verbosity_reminder.COUNTER_FILE", counter_file):
        # Run 1st turn
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0
        assert counter_file.exists()
        assert counter_file.read_text().strip() == "1"
        captured = capsys.readouterr()
        assert "[VERBOSITY]" not in captured.out

        # Run 2nd turn
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0
        assert counter_file.read_text().strip() == "2"
        captured = capsys.readouterr()
        assert "[VERBOSITY]" in captured.out
        assert "Keep responses concise" in captured.out

def test_verbosity_reminder_periodic_turns(tmp_path, capsys):
    counter_file = tmp_path / "verbosity_turn_counter"
    with patch("agentflow.hooks.verbosity_reminder.COUNTER_FILE", counter_file):
        # Turn 3
        counter_file.write_text("2")
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "[VERBOSITY]" not in captured.out

        # Turn 4
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "[VERBOSITY]" in captured.out

        # Turn 5
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "[VERBOSITY]" not in captured.out

        # Turn 6
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "[VERBOSITY]" in captured.out

def test_verbosity_reminder_corrupt_file_resets_gracefully(tmp_path, capsys):
    counter_file = tmp_path / "verbosity_turn_counter"
    counter_file.write_text("not-an-integer-corrupt")

    with patch("agentflow.hooks.verbosity_reminder.COUNTER_FILE", counter_file):
        with pytest.raises(SystemExit):
            main()
        assert counter_file.read_text().strip() == "1"
        captured = capsys.readouterr()
        assert "[VERBOSITY]" not in captured.out


def test_arm_file_off_suppresses_output(tmp_path, capsys, monkeypatch):
    """When arm file contains 'off', no verbosity output even on trigger turn."""
    counter_file = tmp_path / "verbosity_turn_counter"
    arm_file = tmp_path / ".agentflow" / "verbosity_ab_arm.txt"
    arm_file.parent.mkdir(parents=True, exist_ok=True)
    arm_file.write_text("off")

    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    with patch("agentflow.hooks.verbosity_reminder.COUNTER_FILE", counter_file):
        counter_file.write_text("1")  # next call is turn 2 → trigger turn
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "[VERBOSITY]" not in captured.out


def test_arm_file_on_does_not_suppress(tmp_path, capsys, monkeypatch):
    """When arm file contains 'on', normal verbosity output on trigger turn."""
    counter_file = tmp_path / "verbosity_turn_counter"
    arm_file = tmp_path / ".agentflow" / "verbosity_ab_arm.txt"
    arm_file.parent.mkdir(parents=True, exist_ok=True)
    arm_file.write_text("on")

    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    with patch("agentflow.hooks.verbosity_reminder.COUNTER_FILE", counter_file):
        counter_file.write_text("1")  # next call is turn 2 → trigger turn
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "[VERBOSITY]" in captured.out


def test_missing_arm_file_falls_through_to_normal_behavior(tmp_path, capsys, monkeypatch):
    """When arm file is absent, hook behaves normally (no suppression)."""
    counter_file = tmp_path / "verbosity_turn_counter"
    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    # No arm file created — should fall through to normal behavior
    with patch("agentflow.hooks.verbosity_reminder.COUNTER_FILE", counter_file):
        counter_file.write_text("1")  # next call is turn 2 → trigger turn
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "[VERBOSITY]" in captured.out


def test_session_type_detection_orchestrate(tmp_path, monkeypatch):
    """Session type is written to session_state.json when prompt contains /orchestrate."""
    import json
    from io import StringIO

    counter_file = tmp_path / "verbosity_turn_counter"
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "")

    stdin_data = '{"prompt": "/orchestrate my_skill"}'

    with patch("agentflow.hooks.verbosity_reminder.COUNTER_FILE", counter_file):
        with patch("sys.stdin.isatty", return_value=False):
            mock_stdin = StringIO(stdin_data)
            with patch("sys.stdin", mock_stdin):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 0

    # Verify session_state.json was written
    session_state_file = agentflow_dir / "session_state.json"
    assert session_state_file.exists()
    data = json.loads(session_state_file.read_text())
    assert data["session_type"] == "orchestrator"


def test_session_type_detection_oracle(tmp_path, monkeypatch):
    """Session type is written to session_state.json when prompt contains /oracle."""
    import json
    from io import StringIO

    counter_file = tmp_path / "verbosity_turn_counter"
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "")

    stdin_data = '{"prompt": "/oracle design sparring"}'

    with patch("agentflow.hooks.verbosity_reminder.COUNTER_FILE", counter_file):
        with patch("sys.stdin.isatty", return_value=False):
            mock_stdin = StringIO(stdin_data)
            with patch("sys.stdin", mock_stdin):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 0

    # Verify session_state.json was written
    session_state_file = agentflow_dir / "session_state.json"
    assert session_state_file.exists()
    data = json.loads(session_state_file.read_text())
    assert data["session_type"] == "oracle"


def test_session_type_not_written_on_unrelated_prompt(tmp_path, monkeypatch):
    """Session type is NOT written when prompt doesn't contain /oracle or /orchestrate."""
    import json
    from io import StringIO

    counter_file = tmp_path / "verbosity_turn_counter"
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "")

    stdin_data = '{"prompt": "just a normal prompt"}'

    with patch("agentflow.hooks.verbosity_reminder.COUNTER_FILE", counter_file):
        with patch("sys.stdin.isatty", return_value=False):
            mock_stdin = StringIO(stdin_data)
            with patch("sys.stdin", mock_stdin):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 0

    # Verify session_state.json was NOT written
    session_state_file = agentflow_dir / "session_state.json"
    assert not session_state_file.exists()


def test_session_type_with_session_id(tmp_path, monkeypatch):
    """Session type is written to sessions/<sid>/session_state.json when AGENTFLOW_SESSION_ID is set."""
    import json
    from io import StringIO

    counter_file = tmp_path / "verbosity_turn_counter"
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    session_id = "test-session-123"
    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", session_id)

    stdin_data = '{"prompt": "/orchestrate"}'

    with patch("agentflow.hooks.verbosity_reminder.COUNTER_FILE", counter_file):
        with patch("sys.stdin.isatty", return_value=False):
            mock_stdin = StringIO(stdin_data)
            with patch("sys.stdin", mock_stdin):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 0

    # Verify session_state.json was written to sessions/<sid>/
    session_state_file = agentflow_dir / "sessions" / session_id / "session_state.json"
    assert session_state_file.exists()
    data = json.loads(session_state_file.read_text())
    assert data["session_type"] == "orchestrator"
