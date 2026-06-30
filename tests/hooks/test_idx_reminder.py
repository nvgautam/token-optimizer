import os
import hashlib
from unittest.mock import patch

import pytest

from agentflow.hooks.idx_reminder import main


def test_idx_reminder_counter_increments_and_creates_file(tmp_path, capsys):
    counter_file = tmp_path / "idx_turn_counter"
    assert not counter_file.exists()

    with patch("agentflow.hooks.idx_reminder.COUNTER_FILE", counter_file):
        # Run 1st turn
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0
        assert counter_file.exists()
        assert counter_file.read_text().strip() == "1"
        captured = capsys.readouterr()
        assert "[IDX]" not in captured.out

        # Run 2nd turn
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0
        assert counter_file.read_text().strip() == "2"
        captured = capsys.readouterr()
        assert "[IDX]" not in captured.out

        # Run 3rd turn
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0
        assert counter_file.read_text().strip() == "3"
        captured = capsys.readouterr()
        assert "[IDX]" in captured.out
        cwd_hash = hashlib.sha256(os.getcwd().encode()).hexdigest()
        assert f"~/.agentflow/cache/{cwd_hash}/index/<file>.idx" in captured.out


def test_idx_reminder_periodic_turns(tmp_path, capsys):
    counter_file = tmp_path / "idx_turn_counter"
    with patch("agentflow.hooks.idx_reminder.COUNTER_FILE", counter_file):
        # Turn 4
        counter_file.write_text("3")
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "[IDX]" not in captured.out

        # Turn 5
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "[IDX]" not in captured.out

        # Turn 6
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "[IDX]" in captured.out

        # Turn 7
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "[IDX]" not in captured.out

        # Turn 8
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "[IDX]" not in captured.out

        # Turn 9
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "[IDX]" in captured.out


def test_idx_reminder_corrupt_file_resets_gracefully(tmp_path, capsys):
    counter_file = tmp_path / "idx_turn_counter"
    counter_file.write_text("not-an-integer-corrupt")

    with patch("agentflow.hooks.idx_reminder.COUNTER_FILE", counter_file):
        with pytest.raises(SystemExit):
            main()
        assert counter_file.read_text().strip() == "1"
        captured = capsys.readouterr()
        assert "[IDX]" not in captured.out
