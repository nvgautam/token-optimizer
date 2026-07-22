"""Tests for agentflow.shell.audit_logger."""
from __future__ import annotations
import json

from agentflow.shell.audit_logger import scrub, write_audit


def test_scrub_redacts_sensitive_key():
    result = scrub({"token": "abc123secret"})
    assert result["token"] == "[REDACTED]"


def test_scrub_passes_nonsensitive():
    entry = {"event": "foo", "count": 42}
    result = scrub(entry)
    assert result == {"event": "foo", "count": 42}


def test_scrub_nested_dict():
    entry = {"outer": {"password": "s3cr3t", "user": "alice"}, "name": "test"}
    result = scrub(entry)
    assert result["outer"]["password"] == "[REDACTED]"
    assert result["outer"]["user"] == "alice"
    assert result["name"] == "test"


def test_write_audit_appends_jsonl(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    write_audit(log_path, {"event": "test_event"})
    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert "ts" in record
    assert "sid" in record
    assert record["event"] == "test_event"


def test_write_audit_appends_multiple(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    write_audit(log_path, {"event": "first"})
    write_audit(log_path, {"event": "second"})
    lines = log_path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "first"
    assert json.loads(lines[1])["event"] == "second"


def test_write_audit_silent_on_missing_parent(tmp_path):
    log_path = tmp_path / "nonexistent" / "audit.jsonl"
    write_audit(log_path, {"event": "test"})
    assert not log_path.exists()


def test_write_audit_scrubs_before_write(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    write_audit(log_path, {"event": "login", "password": "hunter2"})
    record = json.loads(log_path.read_text())
    assert record["password"] == "[REDACTED]"
    assert record["event"] == "login"


def test_write_audit_sid_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "sess-abc")
    log_path = tmp_path / "audit.jsonl"
    write_audit(log_path, {"event": "x"})
    record = json.loads(log_path.read_text())
    assert record["sid"] == "sess-abc"


def test_scrub_does_not_mutate_original():
    entry = {"token": "secret_value", "event": "e"}
    scrub(entry)
    assert entry["token"] == "secret_value"
