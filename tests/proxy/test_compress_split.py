"""Tests for agentflow.proxy.compress — verify the domain split is correct.

compress.py = request transformers (mutate payload before forwarding)
server.py   = HTTP layer (parse responses, log, forward, handle)
"""

from __future__ import annotations


def test_compress_module_has_request_transformers() -> None:
    """compress.py must export the three payload-mutation functions."""
    from agentflow.proxy.compress import (
        _compress_payload,
        _count_cache_blocks,
        _inject_cache_breakpoints,
    )
    assert callable(_compress_payload)
    assert callable(_count_cache_blocks)
    assert callable(_inject_cache_breakpoints)


def test_headroom_import_fallback() -> None:
    """Headroom availability flag lives in compress.py (it owns the import)."""
    from agentflow.proxy.compress import _HEADROOM_AVAILABLE
    assert isinstance(_HEADROOM_AVAILABLE, bool)


def test_server_has_http_layer_functions() -> None:
    """HTTP-layer functions live in server.py, not compress.py."""
    from agentflow.proxy.server import _parse_usage_from_response, _log_entry
    assert callable(_parse_usage_from_response)
    assert callable(_log_entry)
