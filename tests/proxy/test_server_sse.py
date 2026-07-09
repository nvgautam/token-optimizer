"""Tests for SSE response parsing and usage field extraction."""

import json
from unittest.mock import patch

import pytest

from agentflow.proxy.server import _log_entry, _parse_usage_from_response


class TestParseUsageFromResponse:
    """Test _parse_usage_from_response function."""

    def test_parse_usage_from_sse_response(self):
        """SSE response with message_start event containing complete usage data."""
        sse_body = (
            b"event: message_start\n"
            b'data: {"type":"message_start","message":{"usage":{"input_tokens":100,"output_tokens":50,"cache_read_input_tokens":20,"cache_creation_input_tokens":5}}}\n'
            b"\n"
        )
        result = _parse_usage_from_response(sse_body, "text/event-stream")
        assert result == (50, 20, 5)

    def test_parse_usage_from_sse_missing_fields(self):
        """SSE response with message_start but missing cache fields."""
        sse_body = (
            b"event: message_start\n"
            b'data: {"type":"message_start","message":{"usage":{"input_tokens":100,"output_tokens":50}}}\n'
            b"\n"
        )
        result = _parse_usage_from_response(sse_body, "text/event-stream")
        assert result == (50, 0, 0)

    def test_parse_usage_from_sse_no_message_start(self):
        """SSE response with no message_start event."""
        sse_body = (
            b"event: content_block_start\n"
            b'data: {"type":"content_block_start"}\n'
            b"\n"
        )
        result = _parse_usage_from_response(sse_body, "text/event-stream")
        assert result == (0, 0, 0)

    def test_parse_usage_from_json_response(self):
        """Non-streaming JSON response with usage field."""
        json_body = json.dumps({
            "id": "msg_123",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 75,
                "cache_read_input_tokens": 10,
                "cache_creation_input_tokens": 0,
            },
        }).encode()
        result = _parse_usage_from_response(json_body, "application/json")
        assert result == (75, 10, 0)

    def test_parse_usage_from_json_missing_usage(self):
        """JSON response without usage field."""
        json_body = json.dumps({"id": "msg_123", "content": []}).encode()
        result = _parse_usage_from_response(json_body, "application/json")
        assert result == (0, 0, 0)

    def test_parse_usage_handles_malformed_json(self):
        """Malformed JSON should return defaults."""
        bad_json = b"not valid json"
        result = _parse_usage_from_response(bad_json, "application/json")
        assert result == (0, 0, 0)

    def test_parse_usage_handles_empty_body(self):
        """Empty response body should return defaults."""
        result = _parse_usage_from_response(b"", "application/json")
        assert result == (0, 0, 0)

    def test_parse_usage_sse_with_type_field(self):
        """SSE parsing extracts type correctly and finds message_start."""
        sse_body = (
            b'event: message_start\n'
            b'data: {"type":"message_start","message":{"usage":{"output_tokens":42,"cache_read_input_tokens":3,"cache_creation_input_tokens":1}}}\n'
            b'\n'
        )
        result = _parse_usage_from_response(sse_body, "text/event-stream")
        assert result == (42, 3, 1)


class TestLogEntryWithUsage:
    """Test _log_entry function with usage fields."""

    def test_log_entry_includes_usage_fields(self, tmp_path):
        """Log entry should include all usage fields."""
        with patch("agentflow.proxy.server._project_root", tmp_path):
            _log_entry(
                request_id="test-req-123",
                tokens_before=1000,
                tokens_after=800,
                compression_ratio=0.8,
                output_tokens=50,
                cache_read_input_tokens=20,
                cache_creation_input_tokens=5,
            )

            log_file = tmp_path / ".agentflow" / "proxy_log.jsonl"
            assert log_file.exists()

            content = log_file.read_text()
            record = json.loads(content.strip())

            assert record["request_id"] == "test-req-123"
            assert record["tokens_before"] == 1000
            assert record["tokens_after"] == 800
            assert record["compression_ratio"] == 0.8
            assert record["output_tokens"] == 50
            assert record["cache_read_input_tokens"] == 20
            assert record["cache_creation_input_tokens"] == 5

    def test_log_entry_defaults_usage_to_zero(self, tmp_path):
        """Log entry should default usage fields to 0 if not provided."""
        with patch("agentflow.proxy.server._project_root", tmp_path):
            _log_entry(
                request_id="test-req-456",
                tokens_before=500,
                tokens_after=450,
                compression_ratio=0.9,
            )

            log_file = tmp_path / ".agentflow" / "proxy_log.jsonl"
            assert log_file.exists()

            content = log_file.read_text()
            record = json.loads(content.strip())

            assert record["output_tokens"] == 0
            assert record["cache_read_input_tokens"] == 0
            assert record["cache_creation_input_tokens"] == 0
