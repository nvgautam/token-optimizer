"""AgentFlow compression hooks for headroom library-mode integration.

Protects .idx line-range patterns from compression so symbol index
references are never mangled by the compression pipeline.
"""

from __future__ import annotations

import re
from typing import Any

try:
    from headroom.hooks import CompressionHooks, CompressContext
except ImportError:  # headroom not installed — define stub base
    class CompressContext:  # type: ignore[no-redef]
        pass

    class CompressionHooks:  # type: ignore[no-redef]
        pass


_IDX_PATTERN = re.compile(r"^[A-Za-z_][\w.]*:\d+-\d+$", re.MULTILINE)
_SIGNAL_PATTERN = re.compile(
    r"AGENTFLOW_TASK_(?:COMPLETE|START)|TOKENS: input=|T-\d+",
    re.MULTILINE,
)


def _message_text(msg: dict[str, Any]) -> str:
    """Extract text from a message dict (Anthropic or OpenAI format)."""
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text", "")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


class AgentFlowHooks(CompressionHooks):
    """Assign high bias to messages containing .idx line-range patterns.

    Messages that contain symbol-index references like ``MyClass.method:83-100``
    get bias 999.0 so headroom never compresses them.
    """

    def compute_biases(
        self,
        messages: list[dict[str, Any]],
        ctx: Any = None,
    ) -> dict[int, float]:
        """Return {message_index: 999.0} for messages with .idx patterns."""
        biases: dict[int, float] = {}
        for i, msg in enumerate(messages):
            text = _message_text(msg)
            if _IDX_PATTERN.search(text) or _SIGNAL_PATTERN.search(text):
                biases[i] = 999.0
        return biases
