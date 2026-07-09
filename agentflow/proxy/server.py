"""Thin HTTP proxy that intercepts Claude Code API calls and compresses
messages via headroom library-mode before forwarding to Anthropic.

Run as: python -m agentflow.proxy.server

Startup: prints the bound port number to stdout so ProxyShell can read it.

Security:
- Binds to 127.0.0.1 only (never 0.0.0.0), on ephemeral port :0
- Shared-secret gate: validates X-AgentFlow-Token header against
  AGENTFLOW_PROXY_SECRET env var; returns 401 on mismatch/missing
- Auth headers (x-api-key, Authorization) forwarded verbatim; never logged
- Logs only: {ts, request_id, tokens_before, tokens_after, compression_ratio}
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import httpx

try:
    from headroom.compress import compress
    _HEADROOM_AVAILABLE = True
except ImportError:
    compress = None
    _HEADROOM_AVAILABLE = False

from agentflow.proxy.hooks import AgentFlowHooks

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

_UPSTREAM = "https://api.anthropic.com"
_HOOKS = AgentFlowHooks()

# Resolved at server startup
_project_root: Path = Path.cwd()
_proxy_secret: str = ""


def _parse_usage_from_response(resp_body: bytes, content_type: str) -> tuple[int, int, int]:
    """Parse usage fields from response body.

    Extracts output_tokens, cache_read_input_tokens, cache_creation_input_tokens.
    Returns: (output_tokens, cache_read_input_tokens, cache_creation_input_tokens)
    Defaults to (0, 0, 0) on any parse error.
    """
    if not resp_body:
        return (0, 0, 0)

    # Determine if SSE or JSON based on content-type
    if "text/event-stream" in content_type.lower():
        # Parse SSE response: look for message_start event with usage field
        try:
            text = resp_body.decode("utf-8", errors="replace")
            lines = text.split("\n")
            for line in lines:
                if line.startswith("data:"):
                    data_str = line[5:].strip()  # Remove "data:" prefix
                    try:
                        data = json.loads(data_str)
                        # Look for message_start event type
                        if data.get("type") == "message_start":
                            usage = data.get("message", {}).get("usage", {})
                            output_tokens = int(usage.get("output_tokens", 0))
                            cache_read_input_tokens = int(usage.get("cache_read_input_tokens", 0))
                            cache_creation_input_tokens = int(usage.get("cache_creation_input_tokens", 0))
                            return (output_tokens, cache_read_input_tokens, cache_creation_input_tokens)
                    except (json.JSONDecodeError, ValueError, AttributeError):
                        continue
        except Exception:
            pass
    else:
        # Parse JSON response: extract usage from top-level object
        try:
            data = json.loads(resp_body.decode("utf-8"))
            usage = data.get("usage", {})
            output_tokens = int(usage.get("output_tokens", 0))
            cache_read_input_tokens = int(usage.get("cache_read_input_tokens", 0))
            cache_creation_input_tokens = int(usage.get("cache_creation_input_tokens", 0))
            return (output_tokens, cache_read_input_tokens, cache_creation_input_tokens)
        except (json.JSONDecodeError, ValueError, AttributeError, UnicodeDecodeError):
            pass

    return (0, 0, 0)


def _log_entry(
    request_id: str,
    tokens_before: int,
    tokens_after: int,
    compression_ratio: float,
    output_tokens: int = 0,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> None:
    """Append a single telemetry record to .agentflow/proxy_log.jsonl.

    NEVER writes message content, headers, or user data.
    """
    log_dir = _project_root / ".agentflow"
    try:
        log_dir.mkdir(exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "tokens_before": tokens_before,
            "tokens_after": tokens_after,
            "compression_ratio": compression_ratio,
            "output_tokens": output_tokens,
            "cache_read_input_tokens": cache_read_input_tokens,
            "cache_creation_input_tokens": cache_creation_input_tokens,
        }
        with open(log_dir / "proxy_log.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass  # log failures are non-fatal


class _ProxyHandler(BaseHTTPRequestHandler):
    """Single-endpoint HTTP handler: POST /v1/messages only."""

    def log_message(self, fmt: str, *args: Any) -> None:  # silence access log
        pass

    def _send_401(self) -> None:
        body = b'{"error":"unauthorized"}'
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _validate_secret(self) -> bool:
        token = self.headers.get("X-AgentFlow-Token", "")
        return bool(_proxy_secret) and token == _proxy_secret

    def _drain_body(self) -> bytes:
        """Read and return the full request body."""
        content_length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(content_length) if content_length else b""

    def do_POST(self) -> None:  # noqa: N802
        body = self._drain_body()  # always consume body to avoid connection reset

        try:
            payload: dict[str, Any] = json.loads(body) if body else {}  # type: ignore[arg-type]
        except json.JSONDecodeError:
            payload = {}

        request_id = str(uuid.uuid4())
        messages: list[dict[str, Any]] = payload.get("messages", [])
        model: str = payload.get("model", "claude-sonnet-4-5-20250929")

        tokens_before = 0
        tokens_after = 0
        compression_ratio = 0.0

        if _HEADROOM_AVAILABLE and messages:
            try:
                result = compress(
                    messages,
                    model=model,
                    hooks=_HOOKS,
                    compress_user_messages=False,
                )
                tokens_before = result.tokens_before
                tokens_after = result.tokens_after
                compression_ratio = result.compression_ratio
                payload["messages"] = result.messages
            except Exception:
                pass  # compression failure is non-fatal; forward original

        # Inject cache breakpoints only when headroom is absent — headroom owns
        # cache_control placement as part of its compression pipeline.
        if payload.get("messages") and not _HEADROOM_AVAILABLE:
            existing = _count_cache_blocks(payload)
            payload["messages"] = _inject_cache_breakpoints(payload["messages"], existing)

        # Forward request upstream — pass all original headers verbatim
        # Strip hop-by-hop headers and the proxy shared-secret (never leak to upstream)
        forward_headers: dict[str, str] = {}
        for key, value in self.headers.items():
            lower = key.lower()
            if lower in ("host", "content-length", "transfer-encoding", "x-agentflow-token"):
                continue
            forward_headers[key] = value
        # Request plain (non-compressed) responses so httpx doesn't silently
        # decompress and leave the content-encoding header mismatched on reply.
        forward_headers["accept-encoding"] = "identity"

        try:
            forward_body = json.dumps(payload).encode()
            upstream_url = _UPSTREAM + self.path
            with httpx.Client(timeout=120.0) as client:
                upstream_resp = client.post(
                    upstream_url,
                    content=forward_body,
                    headers=forward_headers,
                )
            status = upstream_resp.status_code
            resp_body = upstream_resp.content
            resp_headers = dict(upstream_resp.headers)
        except Exception as exc:
            logger.warning("Upstream request failed: %s", exc)
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"upstream_failed"}')
            return

        # Extract usage fields from response
        output_tokens, cache_read_input_tokens, cache_creation_input_tokens = _parse_usage_from_response(
            resp_body, resp_headers.get("content-type", "")
        )

        _log_entry(
            request_id,
            tokens_before,
            tokens_after,
            compression_ratio,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
            cache_creation_input_tokens=cache_creation_input_tokens,
        )

        self.send_response(status)
        skip_headers = {"transfer-encoding", "content-length", "connection", "content-encoding"}
        for hdr, val in resp_headers.items():
            if hdr.lower() not in skip_headers:
                self.send_header(hdr, val)
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)


def _count_cache_blocks(payload: dict[str, Any]) -> int:
    """Count existing cache_control blocks across system, tools, and messages."""
    count = 0
    # system: may be a list of blocks
    for block in payload.get("system", []) if isinstance(payload.get("system"), list) else []:
        if isinstance(block, dict) and "cache_control" in block:
            count += 1
    # tools
    for tool in payload.get("tools", []):
        if isinstance(tool, dict) and "cache_control" in tool:
            count += 1
    # messages
    for msg in payload.get("messages", []):
        content = msg.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "cache_control" in block:
                    count += 1
    return count


def _inject_cache_breakpoints(
    messages: list[dict[str, Any]], existing_cache_blocks: int = 0
) -> list[dict[str, Any]]:
    """Inject a cache_control breakpoint at the stable-prefix boundary.

    Skips injection if adding one more would exceed the API limit of 4 blocks.
    """
    _API_CACHE_LIMIT = 4
    if not messages or existing_cache_blocks >= _API_CACHE_LIMIT:
        return messages

    result = [dict(m) for m in messages]

    user_indices = [i for i, m in enumerate(result) if m.get("role") == "user"]

    if len(user_indices) < 2:
        breakpoint_idx = 0 if result else -1
    else:
        # Boundary is the message immediately before the second-to-last user turn
        second_last_user = user_indices[-2]
        breakpoint_idx = second_last_user - 1 if second_last_user > 0 else second_last_user

    if breakpoint_idx < 0:
        return result

    msg = result[breakpoint_idx]
    content = msg.get("content", "")
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    if content:
        last_block = dict(content[-1])
        last_block["cache_control"] = {"type": "ephemeral"}
        content = list(content[:-1]) + [last_block]
    msg = dict(msg)
    msg["content"] = content
    result[breakpoint_idx] = msg
    return result


def _make_server() -> HTTPServer:
    return HTTPServer(("127.0.0.1", 0), _ProxyHandler)


def main() -> None:
    global _project_root, _proxy_secret

    if not _HEADROOM_AVAILABLE:
        import sys
        print("ERROR: headroom not installed — proxy cannot start", file=sys.stderr)
        sys.exit(1)

    _project_root = Path(os.environ.get("AGENTFLOW_PROJECT_ROOT", Path.cwd()))
    _proxy_secret = os.environ.get("AGENTFLOW_PROXY_SECRET", "")

    server = _make_server()
    port = server.server_address[1]
    print(port, flush=True)  # ProxyShell reads this line to learn the port
    server.serve_forever()


if __name__ == "__main__":
    main()
