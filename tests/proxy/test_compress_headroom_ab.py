"""Tests for agentflow.proxy.compress — headroom A/B arm control.

Verifies that when arm="off", compress() is skipped; arm="on" runs normally.
Also tests _read_headroom_arm() for reading the arm state file.
"""

from __future__ import annotations

from unittest.mock import Mock, patch
from pathlib import Path


def test_read_headroom_arm_returns_on_when_file_absent(tmp_path):
    """When .agentflow/verbosity_ab_arm.txt is absent, default to 'on'."""
    from agentflow.proxy.compress import _read_headroom_arm

    arm = _read_headroom_arm(tmp_path)
    assert arm == "on"


def test_read_headroom_arm_reads_file_value_on(tmp_path):
    """When file contains 'on', return 'on'."""
    from agentflow.proxy.compress import _read_headroom_arm

    arm_file = tmp_path / ".agentflow" / "verbosity_ab_arm.txt"
    arm_file.parent.mkdir(parents=True, exist_ok=True)
    arm_file.write_text("on")

    arm = _read_headroom_arm(tmp_path)
    assert arm == "on"


def test_read_headroom_arm_reads_file_value_off(tmp_path):
    """When file contains 'off', return 'off'."""
    from agentflow.proxy.compress import _read_headroom_arm

    arm_file = tmp_path / ".agentflow" / "verbosity_ab_arm.txt"
    arm_file.parent.mkdir(parents=True, exist_ok=True)
    arm_file.write_text("off")

    arm = _read_headroom_arm(tmp_path)
    assert arm == "off"


def test_read_headroom_arm_strips_whitespace(tmp_path):
    """Whitespace is stripped from the read value."""
    from agentflow.proxy.compress import _read_headroom_arm

    arm_file = tmp_path / ".agentflow" / "verbosity_ab_arm.txt"
    arm_file.parent.mkdir(parents=True, exist_ok=True)
    arm_file.write_text("  off  \n")

    arm = _read_headroom_arm(tmp_path)
    assert arm == "off"


def test_read_headroom_arm_handles_unreadable_file(tmp_path):
    """When file is unreadable, default to 'on'."""
    from agentflow.proxy.compress import _read_headroom_arm

    arm_file = tmp_path / ".agentflow" / "verbosity_ab_arm.txt"
    arm_file.parent.mkdir(parents=True, exist_ok=True)
    # Create file and then make it unreadable
    arm_file.write_text("off")
    arm_file.chmod(0o000)

    try:
        arm = _read_headroom_arm(tmp_path)
        assert arm == "on"
    finally:
        arm_file.chmod(0o644)


def test_compress_payload_arm_on_calls_compress(tmp_path):
    """When arm='on', _compress_payload calls the compress_fn."""
    from agentflow.proxy.compress import _compress_payload

    mock_compress_fn = Mock(return_value=Mock(
        tokens_before=100,
        tokens_after=50,
        compression_ratio=0.5,
        messages=[{"role": "user", "content": "compressed"}]
    ))

    payload = {"messages": [{"role": "user", "content": "test"}]}
    msgs = [{"role": "user", "content": "test"}]

    tb, ta, cr = _compress_payload(
        payload,
        msgs,
        model="claude-3-5-sonnet-20241022",
        compress_fn=mock_compress_fn,
        headroom_available=True,
        arm="on"
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
    msgs = [{"role": "user", "content": "test"}]

    tb, ta, cr = _compress_payload(
        payload,
        msgs,
        model="claude-3-5-sonnet-20241022",
        compress_fn=mock_compress_fn,
        headroom_available=True,
        arm="off"
    )

    # compress_fn should NOT be called when arm is "off"
    mock_compress_fn.assert_not_called()
    assert tb == 0
    assert ta == 0
    assert cr == 0.0


def test_compress_payload_arm_off_still_injects_cache_breakpoints(tmp_path):
    """When arm='off' but headroom_available=False, cache breakpoints are injected."""
    from agentflow.proxy.compress import _compress_payload

    mock_compress_fn = Mock()

    payload = {"messages": [
        {"role": "assistant", "content": [{"type": "text", "text": "msg1"}]},
        {"role": "user", "content": [{"type": "text", "text": "msg2"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "msg3"}]},
        {"role": "user", "content": [{"type": "text", "text": "msg4"}]}
    ]}
    msgs = payload["messages"].copy()

    tb, ta, cr = _compress_payload(
        payload,
        msgs,
        model="claude-3-5-sonnet-20241022",
        compress_fn=mock_compress_fn,
        headroom_available=False,
        arm="off"
    )

    # compress_fn should NOT be called
    mock_compress_fn.assert_not_called()
    # But messages should be modified with cache breakpoints
    assert "cache_control" in str(payload["messages"])


def test_compress_payload_arm_defaults_to_on(tmp_path):
    """When arm is not provided, behavior defaults to 'on' (compress runs)."""
    from agentflow.proxy.compress import _compress_payload

    mock_compress_fn = Mock(return_value=Mock(
        tokens_before=100,
        tokens_after=50,
        compression_ratio=0.5,
        messages=[{"role": "user", "content": "compressed"}]
    ))

    payload = {"messages": [{"role": "user", "content": "test"}]}
    msgs = [{"role": "user", "content": "test"}]

    tb, ta, cr = _compress_payload(
        payload,
        msgs,
        model="claude-3-5-sonnet-20241022",
        compress_fn=mock_compress_fn,
        headroom_available=True
        # arm not provided — should default to "on"
    )

    # When arm is not provided, it should default to "on" behavior (compress runs)
    mock_compress_fn.assert_called_once()
    assert tb == 100


def test_compress_payload_headroom_not_available_arm_on(tmp_path):
    """When headroom_available=False, compress_fn is not called regardless of arm."""
    from agentflow.proxy.compress import _compress_payload

    mock_compress_fn = Mock()

    payload = {"messages": [
        {"role": "assistant", "content": [{"type": "text", "text": "msg1"}]},
        {"role": "user", "content": [{"type": "text", "text": "msg2"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "msg3"}]},
        {"role": "user", "content": [{"type": "text", "text": "msg4"}]}
    ]}
    msgs = payload["messages"].copy()

    tb, ta, cr = _compress_payload(
        payload,
        msgs,
        model="claude-3-5-sonnet-20241022",
        compress_fn=mock_compress_fn,
        headroom_available=False,
        arm="on"
    )

    # compress_fn should NOT be called when headroom_available is False
    mock_compress_fn.assert_not_called()
    assert tb == 0
    assert ta == 0
    assert cr == 0.0


def test_compress_payload_compress_exception_handled(tmp_path):
    """When compress_fn raises an exception, it's caught and silently ignored."""
    from agentflow.proxy.compress import _compress_payload

    def mock_compress_fn(*args, **kwargs):
        raise Exception("Test exception")

    payload = {"messages": [{"role": "user", "content": "test"}]}
    msgs = [{"role": "user", "content": "test"}]

    tb, ta, cr = _compress_payload(
        payload,
        msgs,
        model="claude-3-5-sonnet-20241022",
        compress_fn=mock_compress_fn,
        headroom_available=True,
        arm="on"
    )

    # Exception is silently caught
    assert tb == 0
    assert ta == 0
    assert cr == 0.0
    assert payload["messages"] == [{"role": "user", "content": "test"}]


def test_compress_payload_empty_messages_list(tmp_path):
    """When messages list is empty, compress_fn is not called."""
    from agentflow.proxy.compress import _compress_payload

    mock_compress_fn = Mock()

    payload = {"messages": []}
    msgs = []

    tb, ta, cr = _compress_payload(
        payload,
        msgs,
        model="claude-3-5-sonnet-20241022",
        compress_fn=mock_compress_fn,
        headroom_available=True,
        arm="on"
    )

    mock_compress_fn.assert_not_called()
    assert tb == 0
    assert ta == 0
    assert cr == 0.0


def test_compress_payload_arm_off_no_messages_key(tmp_path):
    """When arm='off' and no 'messages' key, function returns zeros."""
    from agentflow.proxy.compress import _compress_payload

    mock_compress_fn = Mock()

    payload = {}  # No messages key
    msgs = []

    tb, ta, cr = _compress_payload(
        payload,
        msgs,
        model="claude-3-5-sonnet-20241022",
        compress_fn=mock_compress_fn,
        headroom_available=True,
        arm="off"
    )

    mock_compress_fn.assert_not_called()
    assert tb == 0
    assert ta == 0
    assert cr == 0.0


def test_compress_payload_with_invalid_arm_defaults_to_on(tmp_path):
    """Invalid arm values default to 'on' behavior."""
    from agentflow.proxy.compress import _compress_payload

    mock_compress_fn = Mock(return_value=Mock(
        tokens_before=100,
        tokens_after=50,
        compression_ratio=0.5,
        messages=[{"role": "user", "content": "compressed"}]
    ))

    payload = {"messages": [{"role": "user", "content": "test"}]}
    msgs = [{"role": "user", "content": "test"}]

    # Invalid arm still defaults to "on"
    tb, ta, cr = _compress_payload(
        payload,
        msgs,
        model="claude-3-5-sonnet-20241022",
        compress_fn=mock_compress_fn,
        headroom_available=True,
        arm=None
    )

    # arm=None should default to "on", so compress runs
    mock_compress_fn.assert_called_once()
    assert tb == 100


def test_compress_payload_defaults_parameters(tmp_path):
    """Test that None parameters trigger default assignments."""
    from agentflow.proxy.compress import _compress_payload

    mock_compress_fn = Mock(return_value=Mock(
        tokens_before=100,
        tokens_after=50,
        compression_ratio=0.5,
        messages=[{"role": "user", "content": "compressed"}]
    ))

    payload = {"messages": [{"role": "user", "content": "test"}]}
    msgs = [{"role": "user", "content": "test"}]

    # Pass None for compress_fn and headroom_available to test defaults
    tb, ta, cr = _compress_payload(
        payload,
        msgs,
        model="claude-3-5-sonnet-20241022",
        compress_fn=None,
        headroom_available=None,
        arm="on"
    )

    # Should work with defaults (assuming headroom is available)
    assert isinstance(tb, int)
    assert isinstance(ta, int)
    assert isinstance(cr, float)
