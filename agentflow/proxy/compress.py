"""Request-transformer helpers for agentflow proxy.

Mutates the outgoing payload BEFORE forwarding to Anthropic:
- headroom compression (removes redundant context)
- cache_control breakpoint injection (when headroom is absent)
- arm-based compression control (A/B testing: on/off)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from headroom.compress import compress
    _HEADROOM_AVAILABLE = True
except ImportError:
    compress = None
    _HEADROOM_AVAILABLE = False

from agentflow.proxy.hooks import AgentFlowHooks

_HOOKS = AgentFlowHooks()


def _read_headroom_arm(project_root: Path | str) -> str:
    """Read the headroom A/B arm from .agentflow/verbosity_ab_arm.txt.

    Returns "on" or "off". Defaults to "on" if file is absent or unreadable.
    """
    arm_file = Path(project_root) / ".agentflow" / "verbosity_ab_arm.txt"
    try:
        arm = arm_file.read_text().strip()
        if arm in ("on", "off"):
            return arm
    except (OSError, IOError):
        pass
    return "on"


def _compress_payload(
    p: dict[str, Any],
    msgs: list[dict[str, Any]],
    model: str,
    compress_fn: Any = None,
    headroom_available: bool | None = None,
    arm: str | None = None,
) -> tuple[int, int, float]:
    """Compress messages in-place and inject cache breakpoints if needed.

    When arm="off", compression is skipped (headroom disabled for A/B testing).
    When arm="on" or None, compression runs normally if headroom_available.

    compress_fn and headroom_available allow the caller (server.py) to pass
    its own module-level references so unit-test patches on server.py take effect.
    """
    if headroom_available is None:
        headroom_available = _HEADROOM_AVAILABLE
    if compress_fn is None:
        compress_fn = compress
    if arm is None:
        arm = "on"
    tb = ta = 0
    cr = 0.0
    if arm == "on" and headroom_available and compress_fn and msgs:
        try:
            r = compress_fn(msgs, model=model, hooks=_HOOKS, compress_user_messages=False)
            tb, ta, cr = r.tokens_before, r.tokens_after, r.compression_ratio
            p["messages"] = r.messages
        except Exception:
            pass
    if p.get("messages") and not headroom_available:
        p["messages"] = _inject_cache_breakpoints(p["messages"], _count_cache_blocks(p))
    return tb, ta, cr


def _count_cache_blocks(payload: dict[str, Any]) -> int:
    """Count existing cache_control blocks across system, tools, and messages."""
    count = 0
    for block in payload.get("system", []) if isinstance(payload.get("system"), list) else []:
        if isinstance(block, dict) and "cache_control" in block:
            count += 1
    for tool in payload.get("tools", []):
        if isinstance(tool, dict) and "cache_control" in tool:
            count += 1
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
