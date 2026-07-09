"""Compression and logging helpers for agentflow proxy.

Handles headroom integration, usage parsing, cache injection, and telemetry
logging for the proxy server's request/response compression pipeline.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from headroom.compress import compress as _compress_headroom
    _HEADROOM_AVAILABLE = True
except ImportError:
    _compress_headroom = None
    _HEADROOM_AVAILABLE = False

# Export the compress function for compatibility
compress = _compress_headroom

logger = logging.getLogger(__name__)


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
    project_root: Path,
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
    log_dir = project_root / ".agentflow"
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
