"""Structured JSON logger for AgentFlow telemetry."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_exporters: list[Callable[[dict], None]] = []


def register_exporter(exporter_fn: Callable[[dict], None]) -> None:
    """Register a callable invoked after each emit. No-op until Stage 2 wires a real exporter."""
    _exporters.append(exporter_fn)


def get_logger(
    trace_id: str | None = None,
    output_path: Path | None = None,
) -> "AgentFlowLogger":
    """Return a logger bound to trace_id. Generates a new uuid4 if trace_id is None."""
    tid = trace_id if trace_id is not None else str(uuid.uuid4())
    path = output_path if output_path is not None else Path(".agentflow") / "telemetry.jsonl"
    return AgentFlowLogger(trace_id=tid, output_path=path)


class AgentFlowLogger:
    """Emits newline-delimited JSON records to a JSONL file."""

    SCHEMA_DEFAULTS: dict[str, Any] = {
        "task_id": None,
        "model": None,
        "tokens_in": 0,
        "tokens_out": 0,
        "duration_ms": 0,
        "status": "ok",
        "metadata": {},
    }

    def __init__(self, trace_id: str, output_path: Path) -> None:
        self.trace_id = trace_id
        self.output_path = output_path

    def emit(self, span: str, **kwargs: Any) -> None:
        """Write one JSON record to output_path. Prompt content must never appear in kwargs."""
        record: dict[str, Any] = {
            "trace_id": self.trace_id,
            "span": span,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
        for field, default in self.SCHEMA_DEFAULTS.items():
            record[field] = kwargs.get(field, default)

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

        for exporter in _exporters:
            exporter(record)
