"""Tests for human_gate_prompt interactive menu."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def human_gate_script():
    """Path to the human_gate_prompt script."""
    return Path(__file__).parent.parent.parent / "agentflow" / "tools" / "human_gate_prompt.py"


class TestHumanGatePrompt:
    """Test the interactive human gate prompt menu."""

    def test_menu_with_valid_input(self, human_gate_script):
        """Test menu selection with valid numbered input."""
        result = subprocess.run(
            [sys.executable, str(human_gate_script), "--options", "yes", "no", "skip"],
            input="1\n",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "yes" in result.stdout.strip()

    def test_menu_with_option_two(self, human_gate_script):
        """Test selecting the second option."""
        result = subprocess.run(
            [sys.executable, str(human_gate_script), "--options", "yes", "no", "skip"],
            input="2\n",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "no" in result.stdout.strip()

    def test_menu_with_option_three(self, human_gate_script):
        """Test selecting the third option."""
        result = subprocess.run(
            [sys.executable, str(human_gate_script), "--options", "yes", "no", "skip"],
            input="3\n",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "skip" in result.stdout.strip()

    def test_invalid_input_retries(self, human_gate_script):
        """Test that invalid input prompts for retry."""
        result = subprocess.run(
            [sys.executable, str(human_gate_script), "--options", "yes", "no"],
            input="5\n1\n",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "yes" in result.stdout.strip()

    def test_invalid_then_valid(self, human_gate_script):
        """Test invalid input followed by valid input."""
        result = subprocess.run(
            [sys.executable, str(human_gate_script), "--options", "merge", "rework"],
            input="0\n2\n",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "rework" in result.stdout.strip()

    def test_with_prompt_text(self, human_gate_script):
        """Test with custom prompt text."""
        result = subprocess.run(
            [
                sys.executable,
                str(human_gate_script),
                "--prompt",
                "Choose action",
                "--options",
                "yes",
                "no",
            ],
            input="1\n",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "yes" in result.stdout.strip()

    def test_no_options_fails(self, human_gate_script):
        """Test that missing options argument fails."""
        result = subprocess.run(
            [sys.executable, str(human_gate_script)],
            input="1\n",
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_single_option(self, human_gate_script):
        """Test with a single option."""
        result = subprocess.run(
            [sys.executable, str(human_gate_script), "--options", "confirm"],
            input="1\n",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "confirm" in result.stdout.strip()

    def test_long_option_names(self, human_gate_script):
        """Test with longer option names."""
        result = subprocess.run(
            [
                sys.executable,
                str(human_gate_script),
                "--options",
                "merge both tasks",
                "merge PR #123 only",
                "provide feedback",
            ],
            input="2\n",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "merge PR #123 only" in result.stdout.strip()
