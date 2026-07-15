"""Request-transformer helpers for agentflow proxy.

Mutates the outgoing payload BEFORE forwarding to Anthropic:
- headroom compression (removes redundant context)
- cache_control breakpoint injection (when headroom is absent)
- arm-based compression control (A/B testing: on/off)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:
    from headroom.compress import compress
    from headroom import CompressConfig
    from headroom.agent_savings import _PROFILES, AGENT_90_PROFILE as _A90_KEY
    _a90 = _PROFILES.get(_A90_KEY)
    _AGENT_90_CONFIG: CompressConfig | None = CompressConfig(
        compress_user_messages=_a90.compress_user_messages,
        compress_system_messages=False,
        protect_recent=6,
        target_ratio=_a90.target_ratio,
        min_tokens_to_compress=_a90.min_tokens_to_compress,
        protect_analysis_context=True,
    ) if _a90 else None
    del _a90
    _HEADROOM_AVAILABLE = True
except ImportError:
    compress = None
    CompressConfig = None  # type: ignore[misc,assignment]
    _AGENT_90_CONFIG = None
    _HEADROOM_AVAILABLE = False

from agentflow.proxy.hooks import AgentFlowHooks
from agentflow.shadow.headroom_ab import record_compression
from agentflow.shell.session_paths import session_file

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


def _is_mid_round(project_root: Path) -> bool:
    """True when tasks_in_flight.json exists and is non-empty (active round)."""
    tif = session_file(
        project_root / ".agentflow",
        "tasks_in_flight.json",
        os.environ.get("AGENTFLOW_SESSION_ID", "")
    )
    if not tif.exists():
        return False
    try:
        return bool(json.loads(tif.read_text("utf-8")))
    except Exception:
        return False


def _compress_payload(
    p: dict[str, Any],
    msgs: list[dict[str, Any]],
    model: str,
    compress_fn: Any = None,
    headroom_available: bool | None = None,
    arm: str | None = None,
    project_root: Path | str | None = None,
) -> tuple[int, int, float]:
    """Compress messages in-place and inject cache breakpoints if needed.

    When arm="off", compression is skipped (headroom disabled for A/B testing).
    When arm is None and project_root is provided, reads arm state from
    .agentflow/verbosity_ab_arm.txt via _read_headroom_arm() so the A/B
    mechanism activates for callers that pass project_root explicitly.
    When project_root=None (server.py live path that doesn't pass project_root),
    arm defaults to "on" for backwards compatibility.

    compress_fn and headroom_available allow the caller (server.py) to pass
    its own module-level references so unit-test patches on server.py take effect.
    """
    if headroom_available is None:
        headroom_available = _HEADROOM_AVAILABLE
    if compress_fn is None:
        compress_fn = compress
    # When project_root is explicitly provided, auto-detect arm from arm file.
    # When project_root=None (server.py live path), default arm to "on" to
    # preserve backwards compatibility until server.py passes project_root.
    if project_root is not None:
        root = Path(project_root)
        if arm is None:
            arm = _read_headroom_arm(root)
    else:
        root = Path.cwd()
        if arm is None:
            arm = "on"
    tb = ta = 0
    cr = 0.0
    if arm == "on" and headroom_available and compress_fn and msgs:
        try:
            if _AGENT_90_CONFIG is not None and not _is_mid_round(root):
                r = compress_fn(msgs, model=model, hooks=_HOOKS, config=_AGENT_90_CONFIG)
            else:
                r = compress_fn(msgs, model=model, hooks=_HOOKS, compress_user_messages=False)
            tb, ta, cr = r.tokens_before, r.tokens_after, r.compression_ratio
            p["messages"] = r.messages
        except Exception:
            pass
    if p.get("messages") and not headroom_available:
        p["messages"] = _inject_cache_breakpoints(p["messages"], _count_cache_blocks(p))
    try:
        record_compression(root, arm, tb, ta)
    except Exception:
        pass  # never fail the hot path on logging errors
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
