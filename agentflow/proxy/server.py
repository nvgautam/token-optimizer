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
    _HEADROOM_AVAILABLE = False

from agentflow.proxy.hooks import AgentFlowHooks

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

_UPSTREAM = "https://api.anthropic.com"
_HOOKS = AgentFlowHooks()

# Resolved at server startup
_project_root: Path = Path.cwd()
_proxy_secret: str = ""


def _log_entry(
    request_id: str,
    tokens_before: int,
    tokens_after: int,
    compression_ratio: float,
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

        # Forward request upstream — pass all original headers verbatim
        # Strip hop-by-hop headers and the proxy shared-secret (never leak to upstream)
        forward_headers: dict[str, str] = {}
        for key, value in self.headers.items():
            lower = key.lower()
            if lower in ("host", "content-length", "transfer-encoding", "x-agentflow-token"):
                continue
            forward_headers[key] = value

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

        _log_entry(request_id, tokens_before, tokens_after, compression_ratio)

        self.send_response(status)
        skip_headers = {"transfer-encoding", "content-length", "connection"}
        for hdr, val in resp_headers.items():
            if hdr.lower() not in skip_headers:
                self.send_header(hdr, val)
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)


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
