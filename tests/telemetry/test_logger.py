"""Tests for T-003: telemetry logger and metrics."""

import json
import uuid
from pathlib import Path

import pytest

import agentflow.telemetry.logger as logger_module
from agentflow.telemetry.logger import AgentFlowLogger, get_logger, register_exporter
from agentflow.telemetry.metrics import emit_metric, new_trace_id

REQUIRED_FIELDS = {"trace_id", "span", "task_id", "model", "tokens_in", "tokens_out",
                   "duration_ms", "status", "metadata"}


@pytest.fixture(autouse=True)
def clear_exporters():
    """Reset global exporter list between tests."""
    original = logger_module._exporters[:]
    logger_module._exporters.clear()
    yield
    logger_module._exporters.clear()
    logger_module._exporters.extend(original)


def _read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_emit_metric_writes_jsonl(tmp_path):
    out = tmp_path / ".agentflow" / "telemetry.jsonl"
    logger = get_logger(output_path=out)
    logger.emit("worker.task", tokens_in=1000, tokens_out=200, status="ok")
    lines = _read_lines(out)
    assert len(lines) == 1


def test_emitted_record_has_all_schema_fields(tmp_path):
    out = tmp_path / ".agentflow" / "telemetry.jsonl"
    logger = get_logger(output_path=out)
    logger.emit("worker.task", tokens_in=1000, tokens_out=200, status="ok")
    record = _read_lines(out)[0]
    assert REQUIRED_FIELDS.issubset(record.keys())


def test_trace_id_propagates(tmp_path):
    out = tmp_path / ".agentflow" / "telemetry.jsonl"
    tid = str(uuid.uuid4())
    logger = get_logger(trace_id=tid, output_path=out)
    logger.emit("oracle.turn")
    logger.emit("oracle.turn")
    records = _read_lines(out)
    assert all(r["trace_id"] == tid for r in records)


def test_missing_optional_fields_default_to_null(tmp_path):
    out = tmp_path / ".agentflow" / "telemetry.jsonl"
    logger = get_logger(output_path=out)
    logger.emit("worker.task")
    record = _read_lines(out)[0]
    assert record["task_id"] is None
    assert record["model"] is None


def test_two_emits_produce_two_lines(tmp_path):
    out = tmp_path / ".agentflow" / "telemetry.jsonl"
    logger = get_logger(output_path=out)
    logger.emit("span.a")
    logger.emit("span.b")
    lines = _read_lines(out)
    assert len(lines) == 2
    assert lines[0]["span"] == "span.a"
    assert lines[1]["span"] == "span.b"


def test_get_logger_no_args_generates_uuid():
    logger = get_logger()
    assert uuid.UUID(logger.trace_id, version=4)


def test_registered_exporter_called_after_emit(tmp_path):
    out = tmp_path / ".agentflow" / "telemetry.jsonl"
    received = []
    register_exporter(received.append)
    logger = get_logger(output_path=out)
    logger.emit("test.span", tokens_in=5)
    assert len(received) == 1
    assert received[0]["span"] == "test.span"
    assert received[0]["tokens_in"] == 5


def test_emit_creates_missing_agentflow_dir(tmp_path):
    out = tmp_path / "nested" / ".agentflow" / "telemetry.jsonl"
    assert not out.parent.exists()
    logger = get_logger(output_path=out)
    logger.emit("init.test")
    assert out.exists()


def test_emit_metric_convenience_wrapper(tmp_path, monkeypatch):
    out = tmp_path / ".agentflow" / "telemetry.jsonl"
    monkeypatch.chdir(tmp_path)
    # emit_metric uses default path relative to cwd
    emit_metric("worker.task", tokens_in=1000, tokens_out=200, status="ok")
    lines = _read_lines(out)
    assert len(lines) == 1
    assert REQUIRED_FIELDS.issubset(lines[0].keys())


def test_new_trace_id_returns_valid_uuid4():
    tid = new_trace_id()
    parsed = uuid.UUID(tid, version=4)
    assert str(parsed) == tid
