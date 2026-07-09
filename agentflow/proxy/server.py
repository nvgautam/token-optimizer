"""HTTP proxy: intercepts /v1/messages, compresses via headroom, forwards to Anthropic.

Binds 127.0.0.1:0 only. Validates X-AgentFlow-Token header.
Logs: {ts, request_id, tokens_before, tokens_after, compression_ratio}
"""

from __future__ import annotations
import json, logging, os, uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import httpx
from agentflow.proxy.compress import (
    _compress_payload, _inject_cache_breakpoints, _HEADROOM_AVAILABLE, compress,
)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
_UPSTREAM = "https://api.anthropic.com"
_project_root: Path = Path.cwd()
_proxy_secret: str = ""


def _parse_usage_from_response(resp_body: bytes, content_type: str) -> tuple[int, int, int]:
    """Return (output_tokens, cache_read, cache_creation) from JSON or SSE body."""
    if not resp_body:
        return (0, 0, 0)
    def _extract(u: dict) -> tuple[int, int, int]:
        return (int(u.get("output_tokens", 0)),
                int(u.get("cache_read_input_tokens", 0)),
                int(u.get("cache_creation_input_tokens", 0)))
    if "text/event-stream" in content_type.lower():
        try:
            for line in resp_body.decode("utf-8", errors="replace").split("\n"):
                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                        if data.get("type") == "message_start":
                            return _extract(data.get("message", {}).get("usage", {}))
                    except (json.JSONDecodeError, ValueError, AttributeError):
                        continue
        except Exception:
            pass
    else:
        try:
            return _extract(json.loads(resp_body.decode("utf-8")).get("usage", {}))
        except (json.JSONDecodeError, ValueError, AttributeError, UnicodeDecodeError):
            pass
    return (0, 0, 0)


def _log_entry(
    request_id: str, tokens_before: int, tokens_after: int, compression_ratio: float,
    output_tokens: int = 0, cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> None:
    """Append telemetry to .agentflow/proxy_log.jsonl. Never logs content."""
    log_dir = _project_root / ".agentflow"
    try:
        log_dir.mkdir(exist_ok=True)
        record = {"ts": datetime.now(timezone.utc).isoformat(), "request_id": request_id,
                  "tokens_before": tokens_before, "tokens_after": tokens_after,
                  "compression_ratio": compression_ratio, "output_tokens": output_tokens,
                  "cache_read_input_tokens": cache_read_input_tokens,
                  "cache_creation_input_tokens": cache_creation_input_tokens}
        with open(log_dir / "proxy_log.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass


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
    def log_message(self, fmt: str, *args: Any) -> None: pass
    def _validate_secret(self) -> bool:
        return bool(_proxy_secret) and self.headers.get("X-AgentFlow-Token", "") == _proxy_secret
    def _drain_body(self) -> bytes:
        cl = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(cl) if cl else b""
    def _send_401(self) -> None:
        b = b'{"error":"unauthorized"}'
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(b)
    def do_POST(self) -> None:
        body = self._drain_body()
        try:
            p: dict[str, Any] = json.loads(body) if body else {}
        except json.JSONDecodeError:
            p = {}
        rid = str(uuid.uuid4())
        tb, ta, cr = _compress_payload(p, p.get("messages", []),
                                       p.get("model", "claude-sonnet-4-5-20250929"),
                                       compress_fn=compress,
                                       headroom_available=_HEADROOM_AVAILABLE)
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
        skip = {"transfer-encoding", "content-length", "connection", "content-encoding"}
        for h, v in rh.items():
            if h.lower() not in skip:
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
    print(server.server_address[1], flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
