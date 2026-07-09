"""Tests for agentflow.proxy.compress — verify split functions are importable."""

from __future__ import annotations


def test_compress_module_imports() -> None:
    """Verify that compression functions are importable from compress.py."""
    from agentflow.proxy.compress import (
        _parse_usage_from_response,
        _log_entry,
    )

    # Verify they are callable
    assert callable(_parse_usage_from_response)
    assert callable(_log_entry)


def test_headroom_import_fallback() -> None:
    """Verify headroom compress import/fallback is accessible."""
    from agentflow.proxy.compress import _HEADROOM_AVAILABLE

    # Should be boolean (regardless of whether headroom is installed)
    assert isinstance(_HEADROOM_AVAILABLE, bool)
