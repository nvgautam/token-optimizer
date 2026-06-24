"""Convenience wrappers for AgentFlow telemetry emission."""

import uuid
from typing import Any

from agentflow.telemetry.logger import get_logger, register_exporter  # noqa: F401


def new_trace_id() -> str:
    """Return a fresh uuid4 string."""
    return str(uuid.uuid4())


def emit_metric(span: str, trace_id: str | None = None, **kwargs: Any) -> None:
    """Emit a telemetry record. Creates a logger bound to trace_id (or a new id)."""
    logger = get_logger(trace_id=trace_id)
    logger.emit(span, **kwargs)
