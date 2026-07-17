"""Tests for agentflow.hooks.fill_utils module."""
import json
import tempfile
from pathlib import Path

import pytest

from agentflow.hooks.fill_utils import compute_fill, extract_fill_from_transcript


class TestComputeFill:
    """Tests for compute_fill function."""

    def test_compute_fill_all_fields(self):
        """Test with all input token fields present."""
        usage = {
            "input_tokens": 100,
            "cache_read_input_tokens": 50,
            "cache_creation_input_tokens": 25,
            "output_tokens": 200,
        }
        assert compute_fill(usage) == 175

    def test_compute_fill_missing_fields(self):
        """Test with missing fields (defaults to 0)."""
        usage = {"input_tokens": 100}
        assert compute_fill(usage) == 100

    def test_compute_fill_empty_dict(self):
        """Test with empty usage dict."""
        assert compute_fill({}) == 0

    def test_compute_fill_ignores_output_tokens(self):
        """Test that output_tokens are not included in computation."""
        usage = {
            "input_tokens": 100,
            "output_tokens": 500,
        }
        assert compute_fill(usage) == 100


class TestExtractFillFromTranscript:
    """Tests for extract_fill_from_transcript function."""

    def test_extract_fill_single_assistant_entry(self):
        """Test extracting fill from a single assistant entry."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "usage": {
                                "input_tokens": 100,
                                "cache_read_input_tokens": 50,
                            }
                        },
                    }
                )
            )
            f.write("\n")
            path = f.name

        try:
            result = extract_fill_from_transcript(path)
            assert result == 150
        finally:
            Path(path).unlink()

    def test_extract_fill_multiple_entries_returns_last(self):
        """Test that the last assistant entry with usage is returned."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {"usage": {"input_tokens": 100}},
                    }
                )
            )
            f.write("\n")
            f.write(
                json.dumps(
                    {
                        "type": "user",
                        "content": "test",
                    }
                )
            )
            f.write("\n")
            f.write(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {"usage": {"input_tokens": 200}},
                    }
                )
            )
            f.write("\n")
            path = f.name

        try:
            result = extract_fill_from_transcript(path)
            assert result == 200
        finally:
            Path(path).unlink()

    def test_extract_fill_no_assistant_entries(self):
        """Test with no assistant entries."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"type": "user", "content": "test"}))
            f.write("\n")
            path = f.name

        try:
            result = extract_fill_from_transcript(path)
            assert result is None
        finally:
            Path(path).unlink()

    def test_extract_fill_assistant_no_usage(self):
        """Test with assistant entry but no usage field."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"type": "assistant", "message": {}}))
            f.write("\n")
            path = f.name

        try:
            result = extract_fill_from_transcript(path)
            assert result is None
        finally:
            Path(path).unlink()

    def test_extract_fill_nonexistent_file(self):
        """Test with nonexistent file."""
        result = extract_fill_from_transcript("/nonexistent/path/file.jsonl")
        assert result is None

    def test_extract_fill_invalid_json(self):
        """Test with invalid JSON lines."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("not valid json\n")
            f.write(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {"usage": {"input_tokens": 100}},
                    }
                )
            )
            f.write("\n")
            path = f.name

        try:
            result = extract_fill_from_transcript(path)
            assert result == 100
        finally:
            Path(path).unlink()

    def test_extract_fill_empty_lines(self):
        """Test with empty lines in transcript."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("\n")
            f.write("\n")
            f.write(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {"usage": {"input_tokens": 75}},
                    }
                )
            )
            f.write("\n")
            path = f.name

        try:
            result = extract_fill_from_transcript(path)
            assert result == 75
        finally:
            Path(path).unlink()
