"""Tests for agentflow.proxy.server — HTTP proxy auth, logging, forwarding."""

from __future__ import annotations

import io
import json
import os
import threading
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_secret() -> str:
    return "test-secret-token-abc123"


@pytest.fixture()
def proxy_server(tmp_path: Path, test_secret: str):
    import agentflow.proxy.server as srv_mod

    old_secret, old_root = srv_mod._proxy_secret, srv_mod._project_root
    srv_mod._proxy_secret = test_secret
    srv_mod._project_root = tmp_path

    server = srv_mod._make_server()
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield server
    server.shutdown()
    t.join(timeout=2)

    srv_mod._proxy_secret = old_secret
    srv_mod._project_root = old_root


def _mock_upstream_ok():
    """Return a context-manager-compatible mock for httpx.Client."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"type":"message"}'
    mock_resp.headers = {"content-type": "application/json"}

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp
    return mock_client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAuthGate:
    def test_accepts_request_without_token(self, proxy_server: HTTPServer):
        """Claude Code sends no X-AgentFlow-Token — proxy must forward without a 401."""
        import httpx
        port = proxy_server.server_address[1]
        with patch("agentflow.proxy.server.httpx.Client", return_value=_mock_upstream_ok()):
            resp = httpx.post(
                f"http://127.0.0.1:{port}/v1/messages",
                json={"messages": [], "model": "claude-sonnet-4-5-20250929"},
            )
        assert resp.status_code == 200

    def test_strips_x_agentflow_token_from_forwarded_headers(self, proxy_server: HTTPServer, test_secret: str):
        """X-AgentFlow-Token must NOT be forwarded to upstream Anthropic API."""
        import httpx
        port = proxy_server.server_address[1]
        mock_client = _mock_upstream_ok()
        with patch("agentflow.proxy.server.httpx.Client", return_value=mock_client):
            httpx.post(
                f"http://127.0.0.1:{port}/v1/messages",
                headers={"X-AgentFlow-Token": test_secret, "x-api-key": "sk-ant-test"},
                json={"messages": [], "model": "claude-sonnet-4-5-20250929"},
            )
        call_kwargs = mock_client.post.call_args
        forwarded_headers = call_kwargs[1].get("headers", {})
        header_keys_lower = {k.lower() for k in forwarded_headers}
        assert "x-agentflow-token" not in header_keys_lower


class TestLogging:
    def test_log_contains_no_content(self, proxy_server: HTTPServer, test_secret: str, tmp_path: Path):
        """proxy_log.jsonl entry has only {ts, request_id, tokens_before, tokens_after, compression_ratio}."""
        import httpx
        port = proxy_server.server_address[1]
        with patch("agentflow.proxy.server.httpx.Client", return_value=_mock_upstream_ok()):
            httpx.post(
                f"http://127.0.0.1:{port}/v1/messages",
                headers={"X-AgentFlow-Token": test_secret},
                json={"messages": [{"role": "user", "content": "secret user content"}],
                      "model": "claude-sonnet-4-5-20250929"},
            )
        log_path = tmp_path / ".agentflow" / "proxy_log.jsonl"
        assert log_path.exists(), "proxy_log.jsonl not written"
        record = json.loads(log_path.read_text().strip())
        allowed_keys = {"ts", "request_id", "tokens_before", "tokens_after", "compression_ratio", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "model"}
        assert set(record.keys()) == allowed_keys

    def test_log_does_not_contain_headers(self, proxy_server: HTTPServer, test_secret: str, tmp_path: Path):
        """Log entry has no auth or other headers."""
        import httpx
        port = proxy_server.server_address[1]
        with patch("agentflow.proxy.server.httpx.Client", return_value=_mock_upstream_ok()):
            httpx.post(
                f"http://127.0.0.1:{port}/v1/messages",
                headers={
                    "X-AgentFlow-Token": test_secret,
                    "Authorization": "Bearer sk-secret",
                    "x-api-key": "sk-secret",
                },
                json={"messages": [], "model": "claude-sonnet-4-5-20250929"},
            )
        log_text = (tmp_path / ".agentflow" / "proxy_log.jsonl").read_text()
        assert "Authorization" not in log_text
        assert "sk-secret" not in log_text


class TestForwarding:
    def test_forwards_auth_headers(self, proxy_server: HTTPServer, test_secret: str):
        """x-api-key and Authorization headers forwarded verbatim."""
        import httpx
        port = proxy_server.server_address[1]
        mock_client = _mock_upstream_ok()
        with patch("agentflow.proxy.server.httpx.Client", return_value=mock_client):
            httpx.post(
                f"http://127.0.0.1:{port}/v1/messages",
                headers={
                    "X-AgentFlow-Token": test_secret,
                    "x-api-key": "sk-ant-test123",
                    "Authorization": "Bearer sk-ant-test123",
                },
                json={"messages": [], "model": "claude-sonnet-4-5-20250929"},
            )
        call_kwargs = mock_client.post.call_args
        forwarded_headers = call_kwargs[1].get("headers", {})
        header_keys_lower = {k.lower() for k in forwarded_headers}
        assert any("api-key" in k for k in header_keys_lower)


class TestBinding:
    def test_binds_loopback_only(self, proxy_server: HTTPServer):
        """Server address is 127.0.0.1 (not 0.0.0.0)."""
        assert proxy_server.server_address[0] == "127.0.0.1"


class TestCompression:
    def test_compression_called_when_messages_present(self, proxy_server: HTTPServer, test_secret: str):
        """compress() is invoked when messages are in the payload."""
        import httpx
        mock_result = MagicMock()
        mock_result.tokens_before = 100
        mock_result.tokens_after = 60
        mock_result.compression_ratio = 0.4
        mock_result.messages = [{"role": "user", "content": "compressed"}]

        port = proxy_server.server_address[1]
        with patch("agentflow.proxy.server.httpx.Client", return_value=_mock_upstream_ok()), \
             patch("agentflow.proxy.server.compress", return_value=mock_result) as mock_compress, \
             patch("agentflow.proxy.server._HEADROOM_AVAILABLE", True):
            httpx.post(
                f"http://127.0.0.1:{port}/v1/messages",
                headers={"X-AgentFlow-Token": test_secret},
                json={"messages": [{"role": "user", "content": "hello"}],
                      "model": "claude-sonnet-4-5-20250929"},
            )
        mock_compress.assert_called_once()

    def test_compression_failure_is_nonfatal(self, proxy_server: HTTPServer, test_secret: str):
        """If compress() raises, the original payload is forwarded."""
        import httpx
        port = proxy_server.server_address[1]
        with patch("agentflow.proxy.server.httpx.Client", return_value=_mock_upstream_ok()), \
             patch("agentflow.proxy.server.compress", side_effect=RuntimeError("boom")), \
             patch("agentflow.proxy.server._HEADROOM_AVAILABLE", True):
            resp = httpx.post(
                f"http://127.0.0.1:{port}/v1/messages",
                headers={"X-AgentFlow-Token": test_secret},
                json={"messages": [{"role": "user", "content": "hello"}],
                      "model": "claude-sonnet-4-5-20250929"},
            )
        assert resp.status_code == 200

    def test_upstream_failure_returns_502(self, proxy_server: HTTPServer, test_secret: str):
        """If upstream call fails, server returns 502."""
        import httpx
        port = proxy_server.server_address[1]
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = Exception("network failure")
        with patch("agentflow.proxy.server.httpx.Client", return_value=mock_client):
            resp = httpx.post(
                f"http://127.0.0.1:{port}/v1/messages",
                headers={"X-AgentFlow-Token": test_secret},
                json={"messages": [], "model": "claude-sonnet-4-5-20250929"},
            )
        assert resp.status_code == 502

    def test_invalid_json_body_handled(self, proxy_server: HTTPServer, test_secret: str):
        """Malformed JSON body is handled gracefully."""
        import httpx
        port = proxy_server.server_address[1]
        with patch("agentflow.proxy.server.httpx.Client", return_value=_mock_upstream_ok()):
            resp = httpx.post(
                f"http://127.0.0.1:{port}/v1/messages",
                headers={"X-AgentFlow-Token": test_secret, "Content-Type": "application/json"},
                content=b"not valid json",
            )
        assert resp.status_code == 200


class TestResponseHeaders:
    def test_content_encoding_stripped_from_response(self, proxy_server: HTTPServer, test_secret: str):
        """Upstream gzip content-encoding must not reach the client — httpx decompresses
        the body but the header would cause the client to double-decompress and fail."""
        import httpx
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"type":"message"}'
        mock_resp.headers = {
            "content-type": "application/json",
            "content-encoding": "gzip",
        }
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp

        port = proxy_server.server_address[1]
        with patch("agentflow.proxy.server.httpx.Client", return_value=mock_client):
            resp = httpx.post(
                f"http://127.0.0.1:{port}/v1/messages",
                headers={"X-AgentFlow-Token": test_secret},
                json={"messages": [], "model": "claude-sonnet-4-5-20250929"},
            )
        assert "content-encoding" not in {k.lower() for k in resp.headers}

    def test_accept_encoding_identity_sent_upstream(self, proxy_server: HTTPServer, test_secret: str):
        """Proxy must request identity encoding from upstream to prevent gzip responses."""
        import httpx
        mock_client = _mock_upstream_ok()
        port = proxy_server.server_address[1]
        with patch("agentflow.proxy.server.httpx.Client", return_value=mock_client):
            httpx.post(
                f"http://127.0.0.1:{port}/v1/messages",
                headers={"X-AgentFlow-Token": test_secret},
                json={"messages": [], "model": "claude-sonnet-4-5-20250929"},
            )
        forwarded_headers = mock_client.post.call_args[1].get("headers", {})
        ae = {k.lower(): v for k, v in forwarded_headers.items()}.get("accept-encoding", "")
        assert ae == "identity"


class TestMain:
    def test_main_exits_when_headroom_unavailable(self):
        """main() raises SystemExit(1) if headroom not installed."""
        import agentflow.proxy.server as srv_mod
        with patch.object(srv_mod, "_HEADROOM_AVAILABLE", False):
            with pytest.raises(SystemExit) as exc_info:
                srv_mod.main()
        assert exc_info.value.code == 1

    def test_main_prints_port_and_serves(self, tmp_path: Path):
        """main() prints port to stdout and calls serve_forever."""
        import sys
        import agentflow.proxy.server as srv_mod
        mock_server = MagicMock()
        mock_server.server_address = ("127.0.0.1", 9999)
        mock_server.serve_forever.side_effect = KeyboardInterrupt

        with patch.object(srv_mod, "_HEADROOM_AVAILABLE", True), \
             patch.object(srv_mod, "_make_server", return_value=mock_server), \
             patch.dict(os.environ, {
                 "AGENTFLOW_PROJECT_ROOT": str(tmp_path),
                 "AGENTFLOW_PROXY_SECRET": "test-secret",
             }):
            captured = io.StringIO()
            old_stdout, sys.stdout = sys.stdout, captured
            try:
                with pytest.raises(KeyboardInterrupt):
                    srv_mod.main()
            finally:
                sys.stdout = old_stdout

        assert "9999" in captured.getvalue()


class TestCacheBreakpoints:
    """Unit tests for _inject_cache_breakpoints."""

    def _fn(self, messages):
        from agentflow.proxy.server import _inject_cache_breakpoints
        return _inject_cache_breakpoints(messages)

    def test_inject_cache_breakpoints_stable_prefix(self):
        """cache_control lands at stable-prefix boundary (before 2nd-to-last user)."""
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "hello"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
            {"role": "user", "content": [{"type": "text", "text": "question"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "answer"}]},
            {"role": "user", "content": [{"type": "text", "text": "final"}]},
        ]
        result = self._fn(messages)
        # user_indices=[0,2,4]; breakpoint_idx=2-1=1 (first assistant)
        assert result[1]["content"][-1].get("cache_control") == {"type": "ephemeral"}
        # Messages outside the breakpoint are untouched
        assert "cache_control" not in result[0]["content"][-1]
        assert "cache_control" not in result[2]["content"][-1]
        assert "cache_control" not in result[4]["content"][-1]

    def test_inject_cache_breakpoints_short_conversation(self):
        """Single user message: breakpoint lands at index 0."""
        messages = [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
        result = self._fn(messages)
        assert result[0]["content"][-1].get("cache_control") == {"type": "ephemeral"}

    def test_inject_cache_breakpoints_empty(self):
        """Empty messages list returns empty list."""
        assert self._fn([]) == []

    def test_inject_cache_breakpoints_string_content_converted(self):
        """String content is converted to list-of-blocks before adding cache_control."""
        messages = [{"role": "user", "content": "hello world"}]
        result = self._fn(messages)
        assert isinstance(result[0]["content"], list)
        last = result[0]["content"][-1]
        assert last["type"] == "text"
        assert last["text"] == "hello world"
        assert last.get("cache_control") == {"type": "ephemeral"}

    def test_inject_cache_breakpoints_idempotent(self):
        """Calling twice produces the same result — no duplicate cache_control entries."""
        messages = [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
        result1 = self._fn(messages)
        result2 = self._fn(result1)
        last = result2[0]["content"][-1]
        assert last.get("cache_control") == {"type": "ephemeral"}
        # Content list length must be unchanged (no extra blocks added)
        assert len(result2[0]["content"]) == len(result1[0]["content"])
