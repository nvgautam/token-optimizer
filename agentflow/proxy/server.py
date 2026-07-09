"""HTTP proxy: intercepts /v1/messages, compresses via headroom, forwards to Anthropic.

Binds 127.0.0.1:0 only. Validates X-AgentFlow-Token header.
Logs: {ts, request_id, tokens_before, tokens_after, compression_ratio}
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import httpx

from agentflow.proxy.compress import (
    _HEADROOM_AVAILABLE,
    _count_cache_blocks,
    _inject_cache_breakpoints,
    _log_entry as _log_entry_impl,
    _parse_usage_from_response,
    compress,
)
from agentflow.proxy.hooks import AgentFlowHooks

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
_UPSTREAM = "https://api.anthropic.com"
_HOOKS = AgentFlowHooks()

_project_root: Path = Path.cwd()
_proxy_secret: str = ""


# Proxy for backward compatibility with tests
def _log_entry(
    request_id: str,
    tokens_before: int,
    tokens_after: int,
    compression_ratio: float,
    output_tokens: int = 0,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> None:
    _log_entry_impl(_project_root, request_id, tokens_before, tokens_after,
                    compression_ratio, output_tokens, cache_read_input_tokens,
                    cache_creation_input_tokens)


def _compress_payload(p: dict[str, Any], msgs: list[dict[str, Any]], model: str
                     ) -> tuple[int, int, float]:
    tb = ta = 0
    cr = 0.0
    if _HEADROOM_AVAILABLE and msgs:
        try:
            r = compress(msgs, model=model, hooks=_HOOKS, compress_user_messages=False)
            tb, ta, cr = r.tokens_before, r.tokens_after, r.compression_ratio
            p["messages"] = r.messages
        except Exception:
            pass
    if p.get("messages") and not _HEADROOM_AVAILABLE:
        p["messages"] = _inject_cache_breakpoints(
            p["messages"], _count_cache_blocks(p))
    return tb, ta, cr


def _forward_request(h: Any, path: str, p: dict[str, Any]) -> tuple[int, bytes, dict]:
    fh = {k: v for k, v in h.items() if k.lower() not in
          ("host", "content-length", "transfer-encoding", "x-agentflow-token")}
    fh["accept-encoding"] = "identity"
    try:
        with httpx.Client(timeout=120.0) as c:
            r = c.post(_UPSTREAM + path, content=json.dumps(p).encode(), headers=fh)
        return r.status_code, r.content, dict(r.headers)
    except Exception as e:
        logger.warning("Upstream request failed: %s", e)
        return 0, b"", {}


class _ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        pass
    def _send_401(self) -> None:
        b = b'{"error":"unauthorized"}'
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(b)
    def _validate_secret(self) -> bool:
        return bool(_proxy_secret) and self.headers.get("X-AgentFlow-Token", "") == _proxy_secret
    def _drain_body(self) -> bytes:
        cl = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(cl) if cl else b""
    def do_POST(self) -> None:
        body = self._drain_body()
        try:
            p = json.loads(body) if body else {}
        except json.JSONDecodeError:
            p = {}
        rid = str(uuid.uuid4())
        tb, ta, cr = _compress_payload(p, p.get("messages", []),
                                       p.get("model", "claude-sonnet-4-5-20250929"))
        s, rb, rh = _forward_request(self.headers, self.path, p)
        if not s:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"upstream_failed"}')
            return
        ot, cr2, cc = _parse_usage_from_response(rb, rh.get("content-type", ""))
        _log_entry(rid, tb, ta, cr, ot, cr2, cc)
        self.send_response(s)
        for h, v in rh.items():
            if h.lower() not in {"transfer-encoding", "content-length", "connection",
                                 "content-encoding"}:
                self.send_header(h, v)
        self.send_header("Content-Length", str(len(rb)))
        self.end_headers()
        self.wfile.write(rb)


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
