"""Tests for agentflow.proxy.compress — headroom A/B arm control.

Verifies that when arm="off", compress() is skipped; arm="on" runs normally.
Tests _read_headroom_arm() for reading the arm state file.
Tests that arm=None auto-detects from the arm file (CRITICAL #1).
Tests that record_compression() is wired into _compress_payload() (CRITICAL #2).
"""

from __future__ import annotations

import json
from unittest.mock import Mock
from pathlib import Path


def test_read_headroom_arm_returns_on_when_file_absent(tmp_path):
    """When .agentflow/verbosity_ab_arm.txt is absent, default to 'on'."""
    from agentflow.proxy.compress import _read_headroom_arm
    assert _read_headroom_arm(tmp_path) == "on"


def test_read_headroom_arm_reads_file_value_off(tmp_path):
    """When file contains 'off', return 'off'."""
    from agentflow.proxy.compress import _read_headroom_arm
    arm_file = tmp_path / ".agentflow" / "verbosity_ab_arm.txt"
    arm_file.parent.mkdir(parents=True, exist_ok=True)
    arm_file.write_text("off")
    assert _read_headroom_arm(tmp_path) == "off"


def test_read_headroom_arm_strips_whitespace(tmp_path):
    """Whitespace is stripped from the read value."""
    from agentflow.proxy.compress import _read_headroom_arm
    arm_file = tmp_path / ".agentflow" / "verbosity_ab_arm.txt"
    arm_file.parent.mkdir(parents=True, exist_ok=True)
    arm_file.write_text("  off  \n")
    assert _read_headroom_arm(tmp_path) == "off"


def test_read_headroom_arm_handles_unreadable_file(tmp_path):
    """When file is unreadable, default to 'on'."""
    from agentflow.proxy.compress import _read_headroom_arm
    arm_file = tmp_path / ".agentflow" / "verbosity_ab_arm.txt"
    arm_file.parent.mkdir(parents=True, exist_ok=True)
    arm_file.write_text("off")
    arm_file.chmod(0o000)
    try:
        assert _read_headroom_arm(tmp_path) == "on"
    finally:
        arm_file.chmod(0o644)


def test_compress_payload_arm_on_calls_compress(tmp_path):
    """When arm='on', _compress_payload calls the compress_fn."""
    from agentflow.proxy.compress import _compress_payload

    mock_compress_fn = Mock(return_value=Mock(
        tokens_before=100, tokens_after=50, compression_ratio=0.5,
        messages=[{"role": "user", "content": "compressed"}]
    ))
    payload = {"messages": [{"role": "user", "content": "test"}]}

    tb, ta, cr = _compress_payload(
        payload, payload["messages"], model="claude-3-5-sonnet-20241022",
        compress_fn=mock_compress_fn, headroom_available=True,
        arm="on", project_root=tmp_path,
    )

    mock_compress_fn.assert_called_once()
    assert tb == 100
    assert ta == 50
    assert cr == 0.5


def test_compress_payload_arm_off_skips_compress(tmp_path):
    """When arm='off', _compress_payload skips compress_fn call."""
    from agentflow.proxy.compress import _compress_payload

    mock_compress_fn = Mock()
    payload = {"messages": [{"role": "user", "content": "test"}]}

    tb, ta, cr = _compress_payload(
        payload, payload["messages"], model="claude-3-5-sonnet-20241022",
        compress_fn=mock_compress_fn, headroom_available=True,
        arm="off", project_root=tmp_path,
    )

    mock_compress_fn.assert_not_called()
    assert tb == 0 and ta == 0 and cr == 0.0


def test_compress_payload_arm_none_autodetects_off_from_file(tmp_path):
    """When arm=None and project_root set, reads arm file; 'off' skips compress (CRITICAL #1)."""
    from agentflow.proxy.compress import _compress_payload

    arm_file = tmp_path / ".agentflow" / "verbosity_ab_arm.txt"
    arm_file.parent.mkdir(parents=True, exist_ok=True)
    arm_file.write_text("off")

    mock_compress_fn = Mock()
    payload = {"messages": [{"role": "user", "content": "test"}]}

    tb, ta, cr = _compress_payload(
        payload, payload["messages"], model="claude-3-5-sonnet-20241022",
        compress_fn=mock_compress_fn, headroom_available=True,
        arm=None, project_root=tmp_path,
    )

    mock_compress_fn.assert_not_called()
    assert tb == 0 and ta == 0 and cr == 0.0


def test_compress_payload_arm_none_defaults_on_when_no_file(tmp_path):
    """When arm=None and no arm file, defaults to 'on' — compress runs (CRITICAL #1)."""
    from agentflow.proxy.compress import _compress_payload

    mock_compress_fn = Mock(return_value=Mock(
        tokens_before=100, tokens_after=50, compression_ratio=0.5,
        messages=[{"role": "user", "content": "compressed"}]
    ))
    payload = {"messages": [{"role": "user", "content": "test"}]}

    tb, ta, cr = _compress_payload(
        payload, payload["messages"], model="claude-3-5-sonnet-20241022",
        compress_fn=mock_compress_fn, headroom_available=True,
        arm=None, project_root=tmp_path,
    )

    mock_compress_fn.assert_called_once()
    assert tb == 100


def test_compress_payload_records_compression_event(tmp_path):
    """_compress_payload writes {arm, tokens_before, tokens_after} to log (CRITICAL #2)."""
    from agentflow.proxy.compress import _compress_payload

    mock_compress_fn = Mock(return_value=Mock(
        tokens_before=100, tokens_after=50, compression_ratio=0.5,
        messages=[{"role": "user", "content": "compressed"}]
    ))
    payload = {"messages": [{"role": "user", "content": "test"}]}

    _compress_payload(
        payload, payload["messages"], model="claude-3-5-sonnet-20241022",
        compress_fn=mock_compress_fn, headroom_available=True,
        arm="on", project_root=tmp_path,
    )

    log_path = tmp_path / ".agentflow" / "headroom_ab_log.jsonl"
    assert log_path.exists()
    entry = json.loads(log_path.read_text().strip())
    assert entry["arm"] == "on"
    assert entry["tokens_before"] == 100
    assert entry["tokens_after"] == 50


def test_compress_payload_records_off_arm_event(tmp_path):
    """When arm='off', records tokens_before=0/tokens_after=0 in log (CRITICAL #2)."""
    from agentflow.proxy.compress import _compress_payload

    mock_compress_fn = Mock()
    payload = {"messages": [{"role": "user", "content": "test"}]}

    _compress_payload(
        payload, payload["messages"], model="claude-3-5-sonnet-20241022",
        compress_fn=mock_compress_fn, headroom_available=True,
        arm="off", project_root=tmp_path,
    )

    log_path = tmp_path / ".agentflow" / "headroom_ab_log.jsonl"
    assert log_path.exists()
    entry = json.loads(log_path.read_text().strip())
    assert entry["arm"] == "off"
    assert entry["tokens_before"] == 0
    assert entry["tokens_after"] == 0


def test_compress_payload_arm_off_still_injects_cache_breakpoints(tmp_path):
    """When arm='off' and headroom_available=False, cache breakpoints are still injected."""
    from agentflow.proxy.compress import _compress_payload

    mock_compress_fn = Mock()
    payload = {"messages": [
        {"role": "assistant", "content": [{"type": "text", "text": "msg1"}]},
        {"role": "user", "content": [{"type": "text", "text": "msg2"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "msg3"}]},
        {"role": "user", "content": [{"type": "text", "text": "msg4"}]}
    ]}

    _compress_payload(
        payload, list(payload["messages"]), model="claude-3-5-sonnet-20241022",
        compress_fn=mock_compress_fn, headroom_available=False,
        arm="off", project_root=tmp_path,
    )

    mock_compress_fn.assert_not_called()
    injected = any(
        isinstance(block, dict) and "cache_control" in block
        for msg in payload["messages"]
        for block in (msg.get("content") if isinstance(msg.get("content"), list) else [])
    )
    assert injected, "Expected a cache_control block to be injected"


def test_compress_payload_compress_exception_handled(tmp_path):
    """When compress_fn raises, exception is silently caught and zeros returned."""
    from agentflow.proxy.compress import _compress_payload

    def failing_compress(*args, **kwargs):
        raise RuntimeError("compress failed")

    payload = {"messages": [{"role": "user", "content": "test"}]}

    tb, ta, cr = _compress_payload(
        payload, payload["messages"], model="claude-3-5-sonnet-20241022",
        compress_fn=failing_compress, headroom_available=True,
        arm="on", project_root=tmp_path,
    )

    assert tb == 0 and ta == 0 and cr == 0.0
    assert payload["messages"] == [{"role": "user", "content": "test"}]


def test_count_cache_blocks_counts_system_and_tools(tmp_path):
    """_count_cache_blocks counts cache_control across system, tools, and messages."""
    from agentflow.proxy.compress import _count_cache_blocks

    payload = {
        "system": [
            {"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": "no cache"},
        ],
        "tools": [
            {"name": "bash", "cache_control": {"type": "ephemeral"}},
            {"name": "read"},
        ],
        "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": "hi", "cache_control": {"type": "ephemeral"}}
            ]}
        ],
    }

    assert _count_cache_blocks(payload) == 3  # 1 system + 1 tool + 1 msg block


def test_inject_cache_breakpoints_skips_when_at_limit(tmp_path):
    """_inject_cache_breakpoints returns messages unchanged when existing blocks >= 4."""
    from agentflow.proxy.compress import _inject_cache_breakpoints

    messages = [{"role": "user", "content": [{"type": "text", "text": "msg"}]}]
    result = _inject_cache_breakpoints(messages, existing_cache_blocks=4)
    assert result == messages


def test_inject_cache_breakpoints_string_content_wrapped(tmp_path):
    """_inject_cache_breakpoints wraps string content and injects cache_control."""
    from agentflow.proxy.compress import _inject_cache_breakpoints

    messages = [{"role": "user", "content": "hello plain string"}]
    result = _inject_cache_breakpoints(messages, existing_cache_blocks=0)
    content = result[0]["content"]
    assert isinstance(content, list)
    assert "cache_control" in content[-1]


def test_inject_cache_breakpoints_empty_messages(tmp_path):
    """_inject_cache_breakpoints returns empty list unchanged."""
    from agentflow.proxy.compress import _inject_cache_breakpoints
    assert _inject_cache_breakpoints([], existing_cache_blocks=0) == []
