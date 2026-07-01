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
